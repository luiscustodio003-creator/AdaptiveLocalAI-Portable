import sys

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hardware import detect_hardware
from launch_planner import launch_plan


def test_hardware_detection_returns_safe_portable_shape():
    result = detect_hardware()
    assert result["system"]
    assert result["machine"]
    assert result["logical_threads"] >= 1
    assert result["memory_source"]
    assert isinstance(result["gpu"]["devices"], list)


def test_launch_plan_uses_physical_cores_when_known():
    plan = launch_plan({
        "logical_threads": 16, "physical_cores": 8,
        "memory_available_bytes": 16 * 1024**3,
    }, {"size_bytes": 2 * 1024**3})
    assert plan["threads"] == 8
    assert plan["gpu_layers"] == 0
    assert 2048 <= plan["context"] <= 16384


def test_launch_plan_does_not_invent_physical_core_count_or_gpu():
    plan = launch_plan({
        "logical_threads": 8, "physical_cores": None,
        "memory_available_bytes": None,
        "gpu": {"detected": True, "usable": False},
    }, "model.gguf")
    assert plan["threads"] == 4
    assert plan["backend"] == "cpu"
    assert plan["gpu_layers"] == 0


def test_launch_plan_clamps_requested_context():
    plan = launch_plan({"logical_threads": 4}, "model.gguf", requested_context=99999)
    assert plan["context"] == 16384
