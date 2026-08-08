# Deploying to production requires passing tests and a human approval.
#
# Lawman selects this file and evaluates data.lawman.decision. It does not read
# input.evidence — the names below, and what they mean, belong to this policy.
package lawman

default allowed := false

allowed if {
	tests_passed
	human_approved
}

tests_passed if input.evidence.tests_passed == true

human_approved if input.evidence.human_approved == true

# Every decision explains itself, including an allowed one. Reasons are
# reported in the order built here.
decision := {
	"allowed": allowed,
	"reasons": array.concat(tests_reason, approval_reason),
}

tests_reason := ["Tests passed."] if tests_passed

tests_reason := ["Tests did not pass, or no test result was presented."] if not tests_passed

approval_reason := ["A human approved this deploy."] if human_approved

approval_reason := ["No human approval was presented."] if not human_approved
