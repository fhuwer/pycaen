#!/usr/bin/env python
"""
Module to control a CAEN 1471 via USB. It supports both the NIM-based module (N1471 or DT1471ET).
Other models N1470 might be supported, but due to missing hardware to test it, this is not
guaranteed to work.
"""
import serial
import re
from enum import Enum
from .exceptions import (
    UnknownCommandError,
    ChannelError,
    ParameterError,
    InvalidReplyError,
)
from time import time


class _HVChannel:
    """
    A single channel of the High Voltage module
    """

    def __init__(self, module, channel):
        """
        Constructor

        Args:
            module (int): ID of the module
            channel (int): Index of the channel
        """
        self.module = module
        self.channel = channel

    @property
    def voltage(self):
        """Target voltage"""
        return self.module._command("MON", "VSET", self.channel, type_=float)

    @voltage.setter
    def voltage(self, voltage):
        self.module._command(
            "SET", "VSET", self.channel, value="{:.1f}".format(voltage)
        )

    @property
    def measured_voltage(self):
        """Retrieve the measured voltage."""
        return self.module._command("MON", "VMON", self.channel, type_=float)

    @property
    def measured_current(self):
        """Retrieve the measured current."""
        return self.module._command("MON", "IMON", self.channel, type_=float)

    @property
    def current_limit(self):
        """Current limit in micro ampere."""
        return self.module._command("MON", "ISET", self.channel, type_=float)

    @current_limit.setter
    def current_limit(self, current):
        self.module._command(
            "SET", "ISET", self.channel, value="{:.1f}".format(current)
        )

    @property
    def imon_range(self):
        """Current range (either HIGH or LOW)"""
        return Caen1471.MonitoringRange(
            self.module._command("MON", "IMRANGE", self.channel)
        )

    @imon_range.setter
    def imon_range(self, value):
        self.module._command("SET", "IMRANGE", self.channel, value.value)

    @property
    def status(self):
        """Get the status of the channel."""
        return Caen1471.ChannelStatus._parse_state(
            self.module._command("MON", "STAT", self.channel, type_=int)
        )

    @property
    def enabled(self):
        """Power the channel on or off."""
        status = self.status
        return (
            status == Caen1471.ChannelStatus.ON
            or status == Caen1471.ChannelStatus.RAMPING_UP
        )

    @enabled.setter
    def enabled(self, value):
        if value:
            self.module._command("SET", "ON", self.channel)
        else:
            self.module._command("SET", "OFF", self.channel)

    @property
    def trip_time(self):
        """Time until the channel goes into trip."""
        return self.module._command("MON", "TRIP", self.channel, type_=float)

    @trip_time.setter
    def trip_time(self, time):
        self.module._command("SET", "TRIP", self.channel, value=time)

    @property
    def voltage_limit(self):
        """Software limit for the voltage."""
        return self.module._command("MON", "MAXV", self.channel, type_=float)

    @voltage_limit.setter
    def voltage_limit(self, limit):
        self.module._command("SET", "MAXV", self.channel, value=limit)

    @property
    def ramp_down_rate(self):
        """Rate for ramping the channel down (in V/s)."""
        return self.module._command("MON", "RDW", self.channel, type_=float)

    @ramp_down_rate.setter
    def ramp_down_rate(self, rate):
        self.module._command("SET", "RDW", self.channel, value=rate)

    @property
    def ramp_up_rate(self):
        """Rate for ramping the channel up (in V/s)."""
        return self.module._command("MON", "RUP", self.channel, type_=float)

    @ramp_up_rate.setter
    def ramp_up_rate(self, rate):
        self.module._command("SET", "RUP", self.channel, value=rate)

    @property
    def power_down_mode(self):
        """How to power the channel down in case of tripping."""
        return self.module._command("MON", "PDWN", self.channel)

    @power_down_mode.setter
    def power_down_mode(self, use_ramp):
        self.module._command("SET", "PDWN", self.channel, value=use_ramp)

    @property
    def polarity(self):
        """Polarity of the channel."""
        return int(f'{self.module._command("MON", "POL", self.channel)}1')


class Caen1471:
    """
    Controller for a CAEN DT1471/N1471 High-Voltage module using the USB interface.
    """

    def __init__(self, port, baud=115200, module=0, num_channels=4):
        """
        Constructor.

        Args:
            port (str): Port for the serial connection.
            baud (int): Baudrate for the serial connection.
            module (int): Module ID of the HV module.
            num_channels (int): Number of channels on the given device.
        """
        self.module = module
        try:
            self.connection = serial.Serial(port, baud, timeout=1)
        except serial.SerialException:
            raise ConnectionError(f"Could not connect to {port}")
        self._num_channels = num_channels
        self.channels = [_HVChannel(self, i) for i in range(num_channels)]
        self.__busy = False

    def is_connected(self):
        """ Check if the serial connection is connected. """ 
        return self.connection is not None and self.connection.is_open

    def disconnect(self):
        if self.connection:
            self.connection.close()

    @property
    def busy(self):
        return self.__busy

    def __check_error(self, reply):
        """
        Parse the reply and raise an error if one occured.

        Args:
            reply (str): Reply from the device.
        """
        if re.match(r"#BD:[0-9]+,CMD:ERR\r\n$", reply):
            raise UnknownCommandError()
        if re.match(r"#BD:[0-9]+,CH:ERR\r\n$", reply):
            raise ChannelError()
        if re.match(r"#BD:[0-9]+,PAR:ERR\r\n$", reply):
            raise ParameterError()
        if re.match(r"#BD:[0-9]+,VAL:ERR\r\n$", reply):
            raise ValueError()
        if re.match(r"#BD:[0-9]+,LOC:ERR\r\n$", reply):
            raise PermissionError("Device is set to LOCAL CONTROL.")

    def _parse_reply(self, reply, type_):
        """
        Parse the reply for errors or results.

        Args:
            reply (str): Reply from the device.
            type_ (class): Type to convert the reply to.
        """
        self.__check_error(reply)

        # Answer on success (with values): "#BD:**,CMD:OK,VAL:*;*;*;*\r\n"
        m = re.match(r"#BD:([0-9]{2}),CMD:OK,VAL:(.*)\r\n", reply.lstrip())
        if m:
            if type_:
                try:
                    return type_(m.group(2))
                except ValueError:
                    raise InvalidReplyError(
                        "The reply could not be cast to the correct type."
                    )
            return m.group(2)
        else:
            return None

    def _command(self, cmd, par, channel=None, value=None, type_=None):
        """
        Send a command to the device.

        Arsg:
            cmd (str): Command to execute.
            par (str): Parameter to set.
            channel (int): Concerning channel.
            value: Value for the command.
            type_ (class): Expected eturn type.
        """
        start = time()
        while self.__busy:
            if time() - start > 5:
                raise TimeoutError("Thread locked for over 5 seconds.")
        self.__busy = True
        if not self.connection or not self.connection.is_open:
            raise ConnectionError()

        # Build command string
        cmd_string = f"$BD:{self.module},CMD:{cmd}"
        if channel is not None:
            cmd_string += f",CH:{channel}"
        cmd_string += f",PAR:{par}"
        if value is not None:
            cmd_string += f",VAL:{value}"
        cmd_string += "\r\n"
        self.connection.write(cmd_string.encode("ascii"))

        response = self._parse_reply(
            self.connection.readline().decode("ascii"), type_=type_
        )
        self.__busy = False
        return response

    @property
    def module_name(self):
        """Name of the module."""
        return self._command("MON", "BDNAME")

    @property
    def firmware_release(self):
        """Installed firmware release."""
        return self._command("MON", "BDFREL")

    @property
    def serial_number(self):
        """Read serial number."""
        return self._command("MON", "BDSNUM")

    @property
    def interlock_status(self):
        """Status of the interlock."""
        return self._command("MON", "BDILK")

    @property
    def interlock_mode(self):
        """Mode of the interlock."""
        return self._command("MON", "BDILKM")

    @interlock_mode.setter
    def interlock_mode(self, value):
        self._command("SET", "BDILKM", value=value)

    @property
    def control_mode(self):
        """Read control mode: local/remote (can only be set on device)."""
        return self._command("MON", "BDCTR")

    @property
    def local_bus_termination(self):
        """Read the bus termination (can only be set on device)."""
        return self._command("MON", "BDTERM") == "ON"

    @property
    def alarm_status(self):
        """Read the alarm status from the device."""
        return Caen1471.AlarmStatus(int(self._command("MON", "BDALARM")))

    def clear_alarm_status(self):
        """Reset the alarm."""
        self._command("SET", "BDCLR")

    class ChannelStatus(Enum):
        """Status of the channel."""

        OFF = 0
        ON = 1
        RAMPING_UP = 2
        RAMPING_DOWN = 3
        OVER_CURRENT = 4
        OVER_VOLTAGE = 5
        UNDER_VOLTAGE = 6
        MAX_VOLTAGE = 7
        TRIPPED = 8
        OVER_POWERED = 9
        OVER_TEMPERATURE = 10
        DISABLED = 11
        KILLED = 12
        INTERLOCKED = 13
        NO_CALIBRATION = 14

        def _parse_state(state):
            for s in reversed(Caen1471.ChannelStatus):
                if s is not Caen1471.ChannelStatus.OFF:
                    if state & (1 << (s.value - 1)):
                        return s
            return Caen1471.ChannelStatus.OFF

    class AlarmStatus(Enum):
        """Possible alarm status codes."""

        NO_ALARM = 0
        CHANNEL_0_ALARM = 1 << 0
        CHANNEL_1_ALARM = 1 << 1
        CHANNEL_2_ALARM = 1 << 2
        CHANNEL_3_ALARM = 1 << 3
        BOARD_POWER_FAIL = 1 << 4
        BOARD_OVER_POWER = 1 << 5
        BOARD_HV_CLOCK_FAIL = 1 << 6

    class MonitoringRange(Enum):
        """Current ranges."""

        LOW = "LOW"
        HIGH = "HIGH"
