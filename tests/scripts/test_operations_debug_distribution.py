"""Release snapshots must exclude executable development tooling."""
import subprocess

from scripts.bundles.payload import snapshot


def test_distribution_snapshot_excludes_development_backend(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "devtools").mkdir()
    (source / "devtools" / "operations_debug.py").write_text("raise RuntimeError('development only')")
    (source / "runtime.py").write_text("value = 'production'")
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                    "-c", "commit.gpgsign=false", "commit", "-qm", "fixture"], cwd=source, check=True)
    destination = tmp_path / "release"
    snapshot(source, "HEAD", destination)
    assert (destination / "runtime.py").is_file()
    assert not (destination / "devtools").exists()
    assert not (destination / ".git").exists()
