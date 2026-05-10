import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent.parent


def test_full_build():
    result = subprocess.run(
        [sys.executable, "build_site.py"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"build_site.py failed:\n{result.stderr}"

    output = REPO / "docs" / "index.html"
    assert output.exists(), "docs/index.html was not created"

    content = output.read_text(encoding="utf-8")
    assert "<!DOCTYPE html>" in content
    assert "TC Kooike" in content
    assert 'id="tab-nav"' in content
    assert 'id="main-content"' in content
    assert "__SCHEDULE_DATA__" not in content, "placeholder was not replaced"
