# Advisory Jules reviews

Lawman can ask Jules to review trusted pull requests automatically. The review is a comment tied to the exact head
commit. It is evidence for a human; it is not a Lawman decision and it never blocks, approves, merges, or requests
changes.

## Setup

1. In the Jules web app, install the Jules GitHub app for this repository.
2. Create a Jules API key in Jules settings.
3. Add the key as the repository Actions secret `JULES_API_KEY`.

The `Jules review` workflow runs when a pull request is opened, reopened, marked ready, or receives a new commit. A
maintainer can also run it manually with **Actions → Jules review → Run workflow** and a pull request number.

Draft pull requests wait until they are marked ready. Pull requests from forks are skipped because GitHub does not
expose repository secrets to untrusted fork workflows. The job summary says why a review was skipped.

## What it does

The workflow gives Jules the pull request's exact head branch and a review-only prompt. It does not include the pull
request title or body in the prompt, enable Jules's automatic pull-request mode, or give Jules permission to change the
repository. The final agent message is posted as one comment identified by the head SHA. Re-running the review for the
same SHA updates that comment.

The Jules API is `v1alpha`. API failures, blocked sessions, malformed responses, missing configuration, and the bounded
20-minute timeout are recorded in the job summary. The review step uses `continue-on-error`, so provider availability
cannot become merge authority accidentally.

The workflow receives only `contents: read` and `pull-requests: write`. Jules remains advisory until a later Lawman
contract explicitly defines how agent-review evidence affects a decision.
