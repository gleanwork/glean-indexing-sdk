import re
from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github/workflows/publish.yml"
WORKFLOWS = REPOSITORY_ROOT / ".github/workflows"
PINNED_ACTION = re.compile(r"[^@\s]+@[0-9a-f]{40}")
PINNED_ACTION_LINE = re.compile(r"\s*-?\s*uses:\s+[^@\s]+@[0-9a-f]{40}\s+#\s+v\d+(?:\.\d+){1,2}\s*")


def load_workflow(path: Path = WORKFLOW_PATH) -> dict[str, Any]:
    return yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return job["steps"]


def step_named(job: dict[str, Any], name: str) -> dict[str, Any]:
    return next(step for step in steps(job) if step.get("name") == name)


def assert_exact_provenance_command(command: str, manifest_option: str) -> None:
    assert '--tag "$RELEASE_TAG"' in command
    assert '--sha "$RELEASE_SHA"' in command
    assert "--dist dist" in command
    assert manifest_option in command
    assert "${{" not in command


def test_publish_is_an_exact_tag_only_workflow() -> None:
    workflow = load_workflow()

    assert workflow["on"] == {"push": {"tags": ["v*"]}}
    assert workflow["env"] == {
        "RELEASE_TAG": "${{ github.ref_name }}",
        "RELEASE_SHA": "${{ github.sha }}",
        "RELEASE_REF": "${{ github.ref }}",
        "RELEASE_BUNDLE_NAME": "release-bundle-${{ github.sha }}",
        "VERIFIED_BUNDLE_NAME": "verified-release-bundle-${{ github.sha }}",
        "RELEASE_NOTES_NAME": "release-notes-${{ github.sha }}",
    }
    assert set(workflow["jobs"]) == {
        "build",
        "verify-bundle",
        "publish-pypi",
        "github-release",
    }


def test_uncredentialed_build_binds_and_transfers_one_verified_bundle() -> None:
    workflow = load_workflow()
    build = workflow["jobs"]["build"]

    assert build["permissions"] == {"actions": "read", "contents": "read"}
    checkout = next(step for step in steps(build) if step["uses"].startswith("actions/checkout@"))
    assert checkout["with"] == {
        "fetch-depth": "0",
        "persist-credentials": "false",
        "ref": "${{ env.RELEASE_REF }}",
    }
    gate = step_named(build, "Require successful CI for the exact release commit")
    gate_index = steps(build).index(gate)
    build_index = steps(build).index(step_named(build, "Build wheel and source distribution once"))
    verify_index = steps(build).index(
        step_named(build, "Verify tag, commit, versions, and artifacts")
    )
    upload_index = steps(build).index(step_named(build, "Transfer verified release bundle"))
    assert gate_index < build_index < verify_index < upload_index
    assert "head_sha: context.sha" in gate["with"]["script"]
    assert gate["timeout-minutes"] == "30"
    assert 'workflow_id: "ci.yml"' in gate["with"]["script"]
    assert 'event: "push"' in gate["with"]["script"]
    assert 'run.conclusion === "success"' in gate["with"]["script"]
    assert "setTimeout" in gate["with"]["script"]
    assert step_named(build, "Build wheel and source distribution once")["run"] == "uv build"
    assert_exact_provenance_command(
        step_named(build, "Verify tag, commit, versions, and artifacts")["run"],
        "--write-manifest release-provenance.json",
    )
    transfer = step_named(build, "Transfer verified release bundle")
    assert transfer["with"]["name"] == "${{ env.RELEASE_BUNDLE_NAME }}"
    assert transfer["with"]["path"].splitlines() == ["dist/", "release-provenance.json"]
    assert transfer["with"]["if-no-files-found"] == "error"
    assert (
        sum(
            step.get("run") == "uv build"
            for job in workflow["jobs"].values()
            for step in steps(job)
        )
        == 1
    )


def test_transferred_bundle_is_reverified_and_repacked_without_oidc() -> None:
    workflow = load_workflow()
    verify = workflow["jobs"]["verify-bundle"]

    assert verify["needs"] == "build"
    assert verify["permissions"] == {"actions": "read", "contents": "read"}
    assert "id-token" not in verify["permissions"]
    checkout = next(step for step in steps(verify) if step["uses"].startswith("actions/checkout@"))
    assert checkout["with"] == {
        "fetch-depth": "0",
        "persist-credentials": "false",
        "ref": "${{ env.RELEASE_REF }}",
    }
    download = step_named(verify, "Download verified release bundle")
    reverify = step_named(verify, "Reverify transferred artifact hashes and provenance")
    upload = step_named(verify, "Transfer reverified release payload")
    notes = step_named(verify, "Generate release notes for the exact tag range")
    notes_upload = step_named(verify, "Transfer release notes")
    assert (
        steps(verify).index(download)
        < steps(verify).index(reverify)
        < steps(verify).index(upload)
        < steps(verify).index(notes)
        < steps(verify).index(notes_upload)
    )
    assert download["with"]["name"] == "${{ env.RELEASE_BUNDLE_NAME }}"
    assert_exact_provenance_command(reverify["run"], "--verify-manifest release-provenance.json")
    assert upload["with"]["name"] == "${{ env.VERIFIED_BUNDLE_NAME }}"
    assert upload["with"]["path"].splitlines() == ["dist/", "release-provenance.json"]
    assert 'find_previous_release_tag.py --current-tag "$RELEASE_TAG"' in notes["run"]
    assert '"${PREVIOUS_TAG}..${RELEASE_TAG}"' in notes["run"]
    assert "${{" not in notes["run"]
    assert notes_upload["with"] == {
        "name": "${{ env.RELEASE_NOTES_NAME }}",
        "path": "release-notes.md",
        "if-no-files-found": "error",
        "retention-days": "1",
    }


def test_pypi_job_has_only_artifact_read_and_oidc_publish_steps() -> None:
    workflow = load_workflow()
    publish = workflow["jobs"]["publish-pypi"]

    assert publish["needs"] == "verify-bundle"
    assert publish["environment"] == "pypi"
    assert publish["permissions"] == {"actions": "read", "id-token": "write"}
    assert [step["name"] for step in steps(publish)] == [
        "Download reverified release payload",
        "Publish verified artifacts to PyPI",
    ]
    assert all("run" not in step for step in steps(publish))
    download, action = steps(publish)
    assert download["with"]["name"] == "${{ env.VERIFIED_BUNDLE_NAME }}"
    assert action["with"]["packages-dir"] == "dist/"


def test_github_release_is_minimal_and_runs_only_after_pypi() -> None:
    workflow = load_workflow()
    release = workflow["jobs"]["github-release"]

    assert release["needs"] == "publish-pypi"
    assert release["permissions"] == {"actions": "read", "contents": "write"}
    assert [step["name"] for step in steps(release)] == [
        "Download reverified release payload",
        "Download prepared release notes",
        "Create GitHub Release after PyPI succeeds",
    ]
    assert all("run" not in step for step in steps(release))
    download, notes, action = steps(release)
    assert download["with"]["name"] == "${{ env.VERIFIED_BUNDLE_NAME }}"
    assert notes["with"]["name"] == "${{ env.RELEASE_NOTES_NAME }}"
    assert action["with"]["tag_name"] == "${{ env.RELEASE_TAG }}"
    assert action["with"]["target_commitish"] == "${{ env.RELEASE_SHA }}"
    assert action["with"]["body_path"] == "release-notes.md"
    assert action["with"]["files"] == "dist/*"


def test_all_workflow_actions_are_sha_pinned_with_version_comments() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        workflow = load_workflow(path)
        action_refs = [
            step["uses"]
            for job in workflow["jobs"].values()
            for step in steps(job)
            if "uses" in step
        ]
        assert action_refs
        assert all(PINNED_ACTION.fullmatch(ref) for ref in action_refs), path

        action_lines = [
            line for line in path.read_text(encoding="utf-8").splitlines() if "uses:" in line
        ]
        assert len(action_lines) == len(action_refs)
        assert all(PINNED_ACTION_LINE.fullmatch(line) for line in action_lines), path


def test_no_workflow_run_script_interpolates_expressions() -> None:
    for path in WORKFLOWS.glob("*.yml"):
        workflow = load_workflow(path)
        run_scripts = [
            step["run"] for job in workflow["jobs"].values() for step in steps(job) if "run" in step
        ]
        assert run_scripts
        assert all("${{" not in script for script in run_scripts), path
