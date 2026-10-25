"""Windows provider boundaries. Physical composition remains separately gated."""

from .native_t102_serial_transport_v1 import (
    WindowsNativeT102SerialTransportError,
    WindowsNativeT102SerialTransportV1,
)
from .calibrated_position_vector_serial_adapter import (
    PositionVectorSerialAdapterError,
    execute_position_vector_serial_exchange,
    load_position_vector_serial_attempt,
)
from .calibrated_position_vector_binding import CalibratedPositionVectorBinding
from .calibrated_position_vector_native_composition import (
    build_calibrated_position_vector_connection,
    execute_owned_calibrated_position_vector_exchange,
    export_position_vector_serial_attempt,
)

__all__ = [
    "CalibratedPositionVectorBinding",
    "PositionVectorSerialAdapterError",
    "WindowsNativeT102SerialTransportError",
    "WindowsNativeT102SerialTransportV1",
    "build_calibrated_position_vector_connection",
    "execute_owned_calibrated_position_vector_exchange",
    "execute_position_vector_serial_exchange",
    "export_position_vector_serial_attempt",
    "load_position_vector_serial_attempt",
]
