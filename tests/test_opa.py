"""Lawman does not decide transitions. OPA does, and Lawman validates it.

Two kinds of test live here. The ones that pin down Lawman's half of the
contract use a stand-in executable, because a correct OPA will not emit two
decisions or die halfway. The ones that prove the integration use the real
pinned OPA, and are skipped only where it is not installed — CI installs it,
so CI runs them.
"""

import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import fake_opa

import lawman
from lawman import Evidence, Intent, LawmanError
from lawman.__main__ import main
from lawman.opa import DECISION_DOCUMENT, EXECUTABLE, evaluate_policy

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "deploy-to-production"
POLICY = ROOT / ".lawman" / "policies" / "deploy-production.rego"
WORKFLOW_DIRECTORY = ROOT / ".github" / "workflows"
CI_WORKFLOW = WORKFLOW_DIRECTORY / "ci.yml"
LAWMAN_WORKFLOW = WORKFLOW_DIRECTORY / "lawman.yml"
DEPLOY = Intent(action="deploy", target="production")
PROVEN = Evidence.from_dict({"tests_passed": True, "human_approved": True})
ALLOWED = {"allowed": True, "reasons": ["The stand-in allowed it."]}

REAL_OPA = shutil.which(EXECUTABLE)
needs_real_opa = unittest.skipUnless(REAL_OPA, "OPA is not installed; CI pins and installs it")


def on_path(directory):
    """Run with exactly one directory on PATH, so `opa` is what a test put there."""
    return mock.patch.dict(os.environ, {"PATH": str(directory)})


def pinned_opa_releases():
    """Every OPA version and checksum pinned by each repository workflow."""
    pattern = re.compile(
        r'OPA_VERSION:\s*"([^"]+)"\s+OPA_SHA256:\s*"([0-9a-f]{64})"'
    )
    workflows = {}
    for workflow in WORKFLOW_DIRECTORY.iterdir():
        if workflow.suffix not in {".yml", ".yaml"}:
            continue
        document = workflow.read_text(encoding="utf-8")
        if "OPA_VERSION" in document:
            workflows[workflow] = pattern.findall(document)
    return workflows


def run_cli(intent, evidence, cwd=ROOT, path=None):
    return subprocess.run(
        [sys.executable, "-m", "lawman", "--intent", str(intent), "--evidence", str(evidence)],
        cwd=cwd,
        env={**os.environ, "PYTHONPATH": str(ROOT), **({} if path is None else {"PATH": path})},
        capture_output=True,
        text=True,
    )


def write(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(document if isinstance(document, str) else json.dumps(document), encoding="utf-8")
    return path


class EvaluatesThroughAnExternalOpa(unittest.TestCase):
    def test_opa_workflows_are_discovered_from_the_directory(self):
        """A future OPA workflow joins pin agreement without a maintained list."""
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            workflow = directory / "nightly.yaml"
            workflow.write_text(
                'env:\n  OPA_VERSION: "1.10.0"\n  OPA_SHA256: "' + "f" * 64 + '"\n',
                encoding="utf-8",
            )
            (directory / "ignored.yml").write_text("name: no OPA here\n", encoding="utf-8")
            with mock.patch(f"{__name__}.WORKFLOW_DIRECTORY", directory):
                releases = pinned_opa_releases()

        self.assertEqual(releases, {workflow: [("1.10.0", "f" * 64)]})

    def test_ci_and_lawman_pin_the_same_opa_release(self):
        """Every workflow evaluates against one identical OPA binary pin."""
        releases = pinned_opa_releases()
        self.assertTrue(
            {CI_WORKFLOW, LAWMAN_WORKFLOW}.issubset(releases),
            "CI and Lawman must both be discovered as OPA workflows",
        )
        pins = []
        for workflow, workflow_pins in releases.items():
            with self.subTest(workflow=workflow.name):
                self.assertEqual(
                    len(workflow_pins), 1, f"{workflow.name} must pin exactly one OPA release"
                )
            if len(workflow_pins) == 1:
                pins.append(workflow_pins[0])
        self.assertEqual(len(pins), len(releases), "every OPA workflow must expose one OPA pin")
        self.assertEqual(
            len(set(pins)),
            1,
            "CI and Lawman must pin the same OPA version and checksum",
        )

    def test_transition_decision_is_evaluated_by_external_opa(self):
        """AC2. The verdict comes out of the OPA process, and nowhere else."""
        refuted = Evidence.from_dict({"tests_passed": False, "human_approved": False})

        # The repository's own policy denies this evidence. A stand-in OPA that
        # allows it is obeyed, so the decision cannot be coming from Python.
        with tempfile.TemporaryDirectory() as directory, on_path(fake_opa.deciding(directory, ALLOWED)):
            decision = evaluate_policy(DEPLOY, POLICY, refuted)

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reasons, ("The stand-in allowed it.",))

        # With no OPA there is no decision. Nothing in Lawman falls back to
        # interpreting the policy itself.
        with tempfile.TemporaryDirectory() as directory, on_path(fake_opa.missing(directory)):
            with self.assertRaises(LawmanError) as refusal:
                evaluate_policy(DEPLOY, POLICY, PROVEN)

        self.assertIn(f"cannot run the OPA executable {EXECUTABLE!r}", str(refusal.exception))

        # And Lawman no longer exposes a transition-policy language of its own.
        for retired in ("Contract", "ContractRegistry", "decide", "select_contract"):
            with self.subTest(retired=retired):
                self.assertFalse(hasattr(lawman, retired))

    def test_opa_receives_intent_and_uninterpreted_evidence(self):
        """AC3. One input document: the validated intent, and the evidence verbatim."""
        facts = {
            "tests_passed": True,
            "coverage": 87.5,
            "reviewers": ["ada", "grace"],
            "release": {"tag": "v2.1.0"},
            "rollback_plan": None,
            "environment": "production",
        }

        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "received.json"
            presented = json.loads(json.dumps(facts))
            evidence = Evidence.from_dict(facts)

            # What was presented is what OPA sees, however the caller's own
            # copy moves in the meantime.
            facts["tests_passed"] = False
            facts["release"]["tag"] = "v9.9.9"
            facts["reviewers"].append("mallory")

            with on_path(fake_opa.deciding(directory, ALLOWED, record=record)):
                evaluate_policy(DEPLOY, POLICY, evidence)
            received = json.loads(record.read_text(encoding="utf-8"))

        self.assertEqual(
            json.loads(received["input"]),
            {"intent": {"action": "deploy", "target": "production"}, "evidence": presented},
        )

        # The policy and the query are the only things Lawman names, and the
        # query is the fixed decision document.
        self.assertEqual(
            received["argv"],
            ["eval", "--format", "json", "--data", str(POLICY), "--stdin-input", DECISION_DOCUMENT],
        )


class RefusesAnythingThatIsNotOneWellFormedDecision(unittest.TestCase):
    """Exit 2, not exit 1. Lawman did not reach a verdict; it could not."""

    def test_invalid_opa_decisions_are_refused(self):
        """AC6. Undefined, empty, multiple, malformed, and schema-invalid decisions."""
        one = {"expressions": [{"value": ALLOWED, "text": DECISION_DOCUMENT}]}
        outputs = {
            "undefined": ("{}", "is undefined"),
            "no result": ('{"result": []}', "exactly one decision"),
            "multiple results": (json.dumps({"result": [one, one]}), "exactly one decision"),
            "multiple expressions": (
                json.dumps({"result": [{"expressions": [one["expressions"][0]] * 2}]}),
                "exactly one decision",
            ),
            "no expressions": (json.dumps({"result": [{"expressions": []}]}), "exactly one decision"),
            "no value": (json.dumps({"result": [{"expressions": [{"text": DECISION_DOCUMENT}]}]}), "no value"),
            "output is not an object": ('["allowed"]', "OPA output must be an object"),
            "result is not an object": (json.dumps({"result": ["allowed"]}), "OPA result must be an object"),
            "empty decision": (json.dumps(fake_opa.envelope({})), "allowed must be true or false"),
            "decision is not an object": (json.dumps(fake_opa.envelope(True)), "policy decision must be an object"),
            "allowed is not boolean": (
                json.dumps(fake_opa.envelope({"allowed": "true", "reasons": ["ok"]})),
                "allowed must be true or false",
            ),
            "no reasons key": (json.dumps(fake_opa.envelope({"allowed": True})), "must be a list of reasons"),
            "no reasons at all": (json.dumps(fake_opa.envelope({"allowed": True, "reasons": []})), "at least one"),
            "blank reason": (
                json.dumps(fake_opa.envelope({"allowed": True, "reasons": ["   "]})),
                "must be a non-empty string",
            ),
            "reason is not a string": (
                json.dumps(fake_opa.envelope({"allowed": False, "reasons": [7]})),
                "must be a non-empty string",
            ),
            "unknown field": (
                json.dumps(fake_opa.envelope({"allowed": True, "reasons": ["ok"], "deny": ["oops"]})),
                "fields Lawman does not understand",
            ),
        }

        for situation, (stdout, expected) in outputs.items():
            with self.subTest(situation=situation), tempfile.TemporaryDirectory() as directory:
                with on_path(fake_opa.install(directory, stdout=stdout)):
                    with self.assertRaises(LawmanError) as refusal:
                        evaluate_policy(DEPLOY, POLICY, PROVEN)
                self.assertIn(expected, str(refusal.exception))

        # Through the CLI: a refusal prints no decision and exits 2.
        with tempfile.TemporaryDirectory() as directory:
            result = run_cli(
                EXAMPLE / "intent.json",
                EXAMPLE / "evidence.json",
                path=fake_opa.install(directory, stdout="{}"),
            )

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn(f"{DECISION_DOCUMENT} is undefined", result.stderr)

    def test_opa_execution_failures_are_refused(self):
        """AC7. Missing, failing, unreadable, and interrupted evaluation."""
        failures = {
            "missing executable": ({}, f"cannot run the OPA executable {EXECUTABLE!r}", True),
            "opa reports its own error": (
                {"stdout": json.dumps({"errors": [{"message": "package expected"}]}), "exit_code": 2},
                "OPA could not evaluate",
                False,
            ),
            "opa fails without saying why": ({"exit_code": 1, "stdout": "{}"}, "exit status 1", False),
            "opa complains on stderr": (
                {"exit_code": 1, "stderr": "no such file or directory\n"},
                "no such file or directory",
                False,
            ),
            "unreadable output": ({"stdout": "not json at all"}, "is not valid JSON", False),
            "output that is not text": ({"stdout": b"\xff\xfe{}"}, "is not readable UTF-8", False),
            "failure explained in bytes that are not text": (
                {"exit_code": 1, "stderr": b"\xff\xfe broke"},
                "exit status 1",
                False,
            ),
            "evaluation is interrupted": ({"interrupted": True, "stdout": "{}"}, "OPA could not evaluate", False),
        }

        for situation, (fake, expected, absent) in failures.items():
            with self.subTest(situation=situation), tempfile.TemporaryDirectory() as directory:
                path = fake_opa.missing(directory) if absent else fake_opa.install(directory, **fake)
                with on_path(path):
                    with self.assertRaises(LawmanError) as refusal:
                        evaluate_policy(DEPLOY, POLICY, PROVEN)
                self.assertIn(expected, str(refusal.exception))

        # An OPA that never finishes cannot hold the gate open. Only the bound
        # is shortened here; the process really is waited on, and really times
        # out.
        with tempfile.TemporaryDirectory() as directory:
            wedged = fake_opa.install(directory, stdout=json.dumps(fake_opa.envelope(ALLOWED)), wedged_for=30)
            with on_path(wedged), mock.patch("lawman.opa.TIMEOUT_SECONDS", 0.5):
                with self.assertRaises(LawmanError) as refusal:
                    evaluate_policy(DEPLOY, POLICY, PROVEN)

        self.assertIn("did not decide", str(refusal.exception))
        self.assertIn("within 0.5 seconds", str(refusal.exception))

        # Through the CLI, each of these is exit 2 with nothing on stdout, not
        # a denial.
        for situation, fake in {
            "missing executable": None,
            "output that is not text": {"stdout": b"\xff\xfe{}"},
        }.items():
            with self.subTest(situation=situation), tempfile.TemporaryDirectory() as directory:
                path = fake_opa.missing(directory) if fake is None else fake_opa.install(directory, **fake)
                result = run_cli(EXAMPLE / "intent.json", EXAMPLE / "evidence.json", path=path)

                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertEqual(len(result.stderr.strip().splitlines()), 1, result.stderr)
                self.assertTrue(result.stderr.startswith("lawman: "), result.stderr)

        # Interrupting Lawman itself, mid-evaluation, is also a refusal.
        stdout, stderr = io.StringIO(), io.StringIO()
        argv = ["--intent", str(EXAMPLE / "intent.json"), "--evidence", str(EXAMPLE / "evidence.json")]
        with mock.patch("subprocess.run", side_effect=KeyboardInterrupt), contextlib.chdir(ROOT):
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(argv)

        self.assertEqual(exit_code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("interrupted before a policy decision was reached", stderr.getvalue())


@needs_real_opa
class TheRealOpaDecides(unittest.TestCase):
    def test_real_pinned_opa_evaluates_the_example_policy(self):
        """AC13. End to end, against the exact OPA version CI installs."""
        ci_pins = pinned_opa_releases()[CI_WORKFLOW]
        self.assertEqual(len(ci_pins), 1, "CI must pin exactly one OPA release")
        version = ci_pins[0][0]
        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        installed = subprocess.run(
            [str(REAL_OPA), "version"], capture_output=True, text=True, check=True
        )
        self.assertIn(f"Version: {version}", installed.stdout)

        allowed = run_cli(EXAMPLE / "intent.json", EXAMPLE / "evidence.json")

        self.assertEqual(allowed.returncode, 0, allowed.stderr)
        self.assertEqual(
            json.loads(allowed.stdout),
            {
                "allowed": True,
                "intent": {"action": "deploy", "target": "production"},
                "reasons": ["Tests passed.", "A human approved this deploy."],
            },
        )

        denied = run_cli(EXAMPLE / "intent.json", EXAMPLE / "evidence-tests-failed.json")

        self.assertEqual(denied.returncode, 1)
        self.assertEqual(
            json.loads(denied.stdout)["reasons"],
            ["Tests did not pass, or no test result was presented.", "A human approved this deploy."],
        )

    def test_changing_only_rego_changes_the_decision(self):
        """AC10. Rules move in Rego. Lawman's Python does not move with them."""
        registry = {"deploy": {"production": "policies/deploy-production.rego"}}
        strict = (
            "package lawman\n\n"
            "default allowed := false\n\n"
            "allowed if input.evidence.signed_off == true\n\n"
            'decision := {"allowed": allowed, "reasons": ["Sign-off decides this repository."]}\n'
        )
        permissive = (
            "package lawman\n\n"
            'decision := {"allowed": true, "reasons": ["This repository allows any deploy."]}\n'
        )
        evidence = {"tests_passed": True, "human_approved": True, "signed_off": False}

        results = {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write(root / "intent.json", {"action": "deploy", "target": "production"})
            write(root / "evidence.json", evidence)
            for name, policy in (("strict", strict), ("permissive", permissive)):
                repository = root / name
                write(repository / ".lawman" / "policies.json", registry)
                write(repository / ".lawman" / "policies" / "deploy-production.rego", policy)
                results[name] = run_cli(root / "intent.json", root / "evidence.json", cwd=repository)

        self.assertEqual(results["strict"].returncode, 1, results["strict"].stderr)
        self.assertEqual(results["permissive"].returncode, 0, results["permissive"].stderr)
        self.assertEqual(
            json.loads(results["permissive"].stdout)["reasons"], ["This repository allows any deploy."]
        )


if __name__ == "__main__":
    unittest.main()
