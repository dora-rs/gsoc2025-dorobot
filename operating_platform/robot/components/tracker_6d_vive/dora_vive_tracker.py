# import logging
# import sys
# import threading
# import time
# from dataclasses import dataclass, field
# import signal

# import pyarrow as pa
# import pysurvive
# from dora import Node

# from tracker_6d_vive.pa_schema import pa_imu_schema as imu_schema
# from tracker_6d_vive.pa_schema import pa_pose_schema as pose_schema

# def shutdown_handler(signum, frame):
#     logger.info(f"Signal {signum} received. Initiating shutdown...")
#     dora_stop_event.set()
#     survive_close_event.set()


# signal.signal(signal.SIGINT, shutdown_handler)
# signal.signal(signal.SIGTERM, shutdown_handler)

# logger = logging.getLogger(__name__)
# node = Node()
# dora_stop_event = threading.Event()
# survive_close_event = threading.Event()

# @dataclass
# class IMUData:
#   """Stores IMU data from Vive trackers with thread-safe access."""

#   _lock: threading.Lock = field(default_factory=threading.Lock)
#   _has_data: bool = False
#   acc: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
#   gyro: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
#   mag: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
#   serial_number: str = ""

#   def update_data(
#     self,
#     serial_number: str,
#     acc: list[float],
#     gyro: list[float],
#     mag: list[float],
#   ) -> None:
#     """Update IMU data."""
#     with self._lock:
#       self.serial_number = serial_number
#       self.acc = acc
#       self.gyro = gyro
#       self.mag = mag
#       self._has_data = True

#   def read_data(self) -> tuple[bool, str, list[float], list[float], list[float]]:
#     """Read IMU data."""
#     with self._lock:
#       return (
#         self._has_data,
#         self.serial_number,
#         self.acc,
#         self.gyro,
#         self.mag,
#       )


# @dataclass
# class PoseData:
#   """Stores Pose data from Vive trackers with thread-safe access."""

#   _lock: threading.Lock = field(default_factory=threading.Lock)
#   _has_data: bool = False
#   position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
#   rotation: list[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
#   serial_number: str = ""

#   def update_data(
#     self,
#     serial_number: str,
#     position: list[float],
#     rotation: list[float],
#   ) -> None:
#     """Update pose data."""
#     with self._lock:
#       self.position = position
#       self.rotation = rotation
#       self.serial_number = serial_number
#       self._has_data = True

#   def read_data(self) -> tuple[bool, str, list[float], list[float]]:
#     """Read pose data."""
#     with self._lock:
#       return self._has_data, self.serial_number, self.position, self.rotation


# def make_imu_func(imu_data: IMUData):  # noqa: ANN201
#   """Returns a closure that handles IMU callbacks from pysurvive."""

#   def imu_func(ctx, _mode, accelgyro: list[float], _timecode, _dev_id) -> None:  # noqa: ANN001
#     acc = accelgyro[:3]
#     gyro = accelgyro[3:6]
#     mag = accelgyro[6:]
#     serial_number = ctx.contents.serial_number.decode("utf-8")
#     imu_data.update_data(serial_number, acc, gyro, mag)

#   return imu_func


# def make_pose_func(pose_data: PoseData):  # noqa: ANN201
#   """Returns a closure that handles Pose callbacks from pysurvive."""

#   def pose_func(ctx, _timecode, pose: list[float]) -> None:  # noqa: ANN001
#     position = pose[:3]
#     rotation = pose[3:]
#     serial_number = ctx.contents.serial_number.decode("utf-8")
#     # serial_number = "TSET serial_number"
#     pose_data.update_data(serial_number, position, rotation)

#   return pose_func


# def receive_data_from_survive(
#   imu_data: IMUData,
#   pose_data: PoseData,
# ) -> None:
#   """Polls pysurvive context for IMU and Pose data."""
#   ctx = pysurvive.init(sys.argv)
#   if ctx is None:
#     logger.error("Vive device not connected.")
#     survive_close_event.set()
#     return

#   try:
#     pysurvive.install_imu_fn(ctx, make_imu_func(imu_data))
#     pysurvive.install_pose_fn(ctx, make_pose_func(pose_data))

#     while not dora_stop_event.is_set():
#       if pysurvive.survive_poll(ctx) != 0:
#         logger.error("Error polling from pysurvive.")
#         survive_close_event.set()
#         break
#       time.sleep(0.001)
#   except Exception as e:
#     logger.exception("Survive error: %s", e)
#     survive_close_event.set()
#   finally:
#     pysurvive.survive_close(ctx)


# def send_data_through_dora(imu_data: IMUData, pose_data: PoseData) -> None:
#   try:
#     for event in node:
#       if dora_stop_event.is_set() or survive_close_event.is_set():
#         break

#       if event["type"] == "INPUT" and event["id"] == "tick":
#         has_imu, sn_imu, acc, gyro, mag = imu_data.read_data()
#         has_pose, sn_pose, pos, rot = pose_data.read_data()

#         if has_imu:
#           imu_batch = pa.record_batch(
#             {
#               "serial_number": [sn_imu],
#               "acc": [acc],
#               "gyro": [gyro],
#               "mag": [mag],
#             },
#             schema=imu_schema,
#           )
#           node.send_output("imu", imu_batch)

#         if has_pose:
#           pose_batch = pa.record_batch(
#             {
#               "serial_number": [sn_pose],
#               "position": [pos],
#               "rotation": [rot],
#             },
#             schema=pose_schema,
#           )
#           node.send_output("pose", pose_batch)

#         time.sleep(0.01)

#       elif event["type"] == "STOP":
#         dora_stop_event.set()
#         break

#   except Exception as e:
#       logger.exception("Dora error: %s", e)


# def main() -> None:
#   """Main entry point."""
#   imu_data = IMUData()
#   pose_data = PoseData()


#   # Start threads
#   survive_thread = threading.Thread(
#     target=receive_data_from_survive,
#     args=(imu_data, pose_data),
#     daemon=True
#   )
#   dora_thread = threading.Thread(
#     target=send_data_through_dora,
#     args=(imu_data, pose_data),
#     daemon=True
#   )

#   survive_thread.start()
#   dora_thread.start()

#   dora_thread.join()
#   survive_thread.join()
  


# if __name__ == "__main__":
#   main()


import logging
import sys
import threading
import time
import signal

from dataclasses import dataclass, field

import pyarrow as pa
import pysurvive
from dora import Node

from tracker_6d_vive.pa_schema import pa_imu_schema as imu_schema
from tracker_6d_vive.pa_schema import pa_pose_schema as pose_schema


logger = logging.getLogger(__name__)
node = Node()
dora_stop_event = threading.Event()
survive_close_event = threading.Event()


@dataclass
class IMUData:
    """Stores IMU data from Vive trackers with thread-safe access."""
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _has_data: bool = False
    acc: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    gyro: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    mag: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    serial_number: str = ""

    def update_data(
        self,
        serial_number: str,
        acc: list[float],
        gyro: list[float],
        mag: list[float],
    ) -> None:
        with self._lock:
            self.serial_number = serial_number
            self.acc = acc
            self.gyro = gyro
            self.mag = mag
            self._has_data = True

    def read_data(self) -> tuple[bool, str, list[float], list[float], list[float]]:
        with self._lock:
            return (
                self._has_data,
                self.serial_number,
                self.acc,
                self.gyro,
                self.mag,
            )


@dataclass
class PoseData:
    """Stores Pose data from Vive trackers with thread-safe access."""
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _has_data: bool = False
    position: list[float] = field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    serial_number: str = ""

    def update_data(
        self,
        serial_number: str,
        position: list[float],
        rotation: list[float],
    ) -> None:
        with self._lock:
            self.position = position
            self.rotation = rotation
            self.serial_number = serial_number
            self._has_data = True

    def read_data(self) -> tuple[bool, str, list[float], list[float]]:
        with self._lock:
            return self._has_data, self.serial_number, self.position, self.rotation


def make_imu_func(imu_data: IMUData):
    def imu_func(ctx, _mode, accelgyro: list[float], _timecode, _dev_id) -> None:
        acc = accelgyro[:3]
        gyro = accelgyro[3:6]
        mag = accelgyro[6:]
        serial_number = ctx.contents.serial_number.decode("utf-8")
        imu_data.update_data(serial_number, acc, gyro, mag)

    return imu_func


def make_pose_func(pose_data: PoseData):
    def pose_func(ctx, _timecode, pose: list[float]) -> None:
        position = pose[:3]
        rotation = pose[3:]
        serial_number = ctx.contents.serial_number.decode("utf-8")
        pose_data.update_data(serial_number, position, rotation)

    return pose_func


def receive_data_from_survive(imu_data: IMUData, pose_data: PoseData) -> None:
    logger.info("Starting Survive thread.")
    ctx = pysurvive.init(sys.argv)
    if ctx is None:
        logger.error("Vive device not connected.")
        survive_close_event.set()
        return

    try:
        pysurvive.install_imu_fn(ctx, make_imu_func(imu_data))
        pysurvive.install_pose_fn(ctx, make_pose_func(pose_data))

        while not dora_stop_event.is_set():
            if pysurvive.survive_poll(ctx) != 0:
                logger.error("Error polling from pysurvive.")
                survive_close_event.set()
                break
            time.sleep(0.001)
    except Exception as e:
        logger.exception("Survive error: %s", e)
        survive_close_event.set()
    finally:
        logger.info("Closing pysurvive context.")
        pysurvive.survive_close(ctx)


def send_data_through_dora(imu_data: IMUData, pose_data: PoseData) -> None:
    logger.info("Starting Dora thread.")
    try:
        for event in node:
            if dora_stop_event.is_set() or survive_close_event.is_set():
                logger.info("Dora loop received stop signal.")
                break

            if event["type"] == "INPUT" and event["id"] == "tick":
                has_imu, sn_imu, acc, gyro, mag = imu_data.read_data()
                has_pose, sn_pose, pos, rot = pose_data.read_data()

                if has_imu:
                    imu_batch = pa.record_batch(
                        {
                            "serial_number": [sn_imu],
                            "acc": [acc],
                            "gyro": [gyro],
                            "mag": [mag],
                        },
                        schema=imu_schema,
                    )
                    node.send_output("imu", imu_batch)

                if has_pose:
                    pose_batch = pa.record_batch(
                        {
                            "serial_number": [sn_pose],
                            "position": [pos],
                            "rotation": [rot],
                        },
                        schema=pose_schema,
                    )
                    node.send_output("pose", pose_batch)

                time.sleep(0.01)

            elif event["type"] == "STOP":
                dora_stop_event.set()
                break

    except Exception as e:
        logger.exception("Dora error: %s", e)
    finally:
        logger.info("Exiting Dora thread.")


def main() -> None:
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    imu_data = IMUData()
    pose_data = PoseData()

    # 设置信号处理函数
    def shutdown_handler(signum, frame):
        logger.info(f"Signal {signum} received. Initiating shutdown...")
        dora_stop_event.set()
        survive_close_event.set()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # 启动线程
    survive_thread = threading.Thread(
        target=receive_data_from_survive,
        args=(imu_data, pose_data),
        daemon=False,
    )
    dora_thread = threading.Thread(
        target=send_data_through_dora,
        args=(imu_data, pose_data),
        daemon=False,
    )

    survive_thread.start()
    dora_thread.start()

    logger.info("All threads started.")

    try:
        # 等待线程结束（设置超时避免卡死）
        survive_thread.join(timeout=5)
        dora_thread.join(timeout=5)

        # 强制退出
        if survive_thread.is_alive():
            logger.warning("Survive thread did not terminate, forcing exit.")
        if dora_thread.is_alive():
            logger.warning("Dora thread did not terminate, forcing exit.")
    except KeyboardInterrupt:
        logger.info("Main thread received Ctrl+C again. Forcing exit.")
        sys.exit(1)
    finally:
        logger.info("Program exiting gracefully.")
        sys.exit(0)


if __name__ == "__main__":
    main()