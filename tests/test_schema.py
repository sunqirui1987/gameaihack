from gameaihack.ingest import PackageInfo
from gameaihack.fingerprint import Fingerprint
from gameaihack.content.ir import build_ir, validate_ir


def test_phase0_ir_validates():
    ir = build_ir(
        job_id="j1",
        pkg=PackageInfo(name="com.example.game"),
        fp=Fingerprint(engine="unity", script_backend="il2cpp"),
        sha256="abc",
        input_profile={"score": 80, "warnings": [], "files": []},
    )
    assert validate_ir(ir) == []
    assert len(ir["radar"]) == 20
    assert ir["radar"][0]["dimension"] == "identity"
    assert ir["radar"][-1]["dimension"] == "tech"
