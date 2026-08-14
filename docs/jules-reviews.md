# Advisory Jules reviews

Lawman can ask Jules to review trusted pull requests automatically. The review is a comment tied to the exact head
commit. It is evidence for a human, not a Lawman decision or merge gate. The workflow itself does not approve, merge,
or request changes.

## Setup

1. In the Jules web app, install the Jules GitHub app for this repository.
2. Create a Jules API key in Jules settings.
3. Add the key as the repository Actions secret `JULES_API_KEY`.

The `Jules review` workflow runs for pull requests targeting `main` when they are opened, reopened, marked ready, or
receive a new commit. A maintainer can also run it manually from the repository's default branch with **Actions →
Jules review → Run workflow** and a pull request number.

Draft pull requests wait until they are marked ready. Pull requests from forks are skipped by the secret-free guard;
the job summary says why, and the Jules credential is never supplied to their workflow job.

## What it does

The workflow gives Jules the pull request's head branch and exact head SHA in a review-only prompt. Before publishing,
it requires structured Jules shell evidence that the last command before the final message verified that SHA. It does
not include the pull request title or body in the prompt, and the Jules API's default no-automation mode does not
automatically create a pull request. The final agent message is posted as one comment identified by the head SHA.
Re-running the review for the same SHA updates that comment.

GitHub runs automatic reviews with `pull_request_target`, restricted to the protected `main` branch. A secret-free
guard job loads the current default-branch implementation and rejects drafts and forks. Only a reviewable pull request
starts the second job that receives the Jules credential, and that job also runs the current default-branch
implementation. The GitHub Actions jobs never execute pull-request code.

Jules does execute shell commands against its pull-request checkout in the provider environment. The no-change,
no-approval, and no-merge constraints are instructions to Jules, not a capability sandbox around the installed Jules
GitHub App. The workflow token permissions do not narrow that app's separately configured repository access.

The Jules API is `v1alpha`. API failures, blocked sessions, malformed responses, missing configuration, repeated or
excessive pagination, and failure to prove the reviewed SHA are recorded in the job summary. Provider polling stops
after 20 minutes, and the complete review step has a 22-minute hard limit. The step uses `continue-on-error`, so
provider availability cannot become merge authority accidentally.

The workflow receives only `contents: read` and `pull-requests: write`. Jules remains advisory until a later Lawman
contract explicitly defines how agent-review evidence affects a decision.
