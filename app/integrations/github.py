import httpx
from app.config import settings
from app.models.session import FileChange
import logging

logger = logging.getLogger(__name__)

GITHUB_API_BASE = "https://api.github.com"

# File patterns to skip during review
SKIP_PATTERNS = [
    ".lock",
    ".min.js",
    ".min.css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    "package-lock.json",
    "yarn.lock",
    "Cargo.lock",
    "poetry.lock",
    "pnpm-lock.yaml",
    "Pipfile.lock",
    ".pyc",
    "__pycache__",
    ".git",
    ".exe",
    ".dll",
    ".so",
    ".dylib",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
]


def _get_headers() -> dict:
    """Get headers for GitHub API requests."""
    return {
        "Authorization": f"token {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def should_review_file(filename: str) -> bool:
    """Check if file should be reviewed."""
    filename_lower = filename.lower()
    return not any(pattern in filename_lower for pattern in SKIP_PATTERNS)


async def get_pr_files(owner: str, repo: str, pr_number: int) -> list[FileChange]:
    """
    Fetch files changed in a pull request.

    Returns list of FileChange objects for reviewable files.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, headers=_get_headers())
        response.raise_for_status()
        files_data = response.json()

    files = []
    for f in files_data:
        filename = f.get("filename", "")

        if not should_review_file(filename):
            logger.debug(f"Skipping file: {filename}")
            continue

        # Truncate very large patches (> 10KB)
        patch = f.get("patch", "")
        if len(patch) > 10000:
            patch = patch[:10000] + "\n... [truncated]"

        files.append(
            FileChange(
                path=filename,
                status=f.get("status", "modified"),
                patch=patch,
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
            )
        )

    logger.info(f"Fetched {len(files)} reviewable files from PR #{pr_number}")
    return files


async def get_pr_details(owner: str, repo: str, pr_number: int) -> dict:
    """Fetch PR metadata."""
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, headers=_get_headers())
        response.raise_for_status()
        return response.json()


async def post_pr_review(
    owner: str, repo: str, pr_number: int, body: str, event: str = "COMMENT"
) -> int:
    """
    Post a review comment to a PR.

    event: COMMENT, APPROVE, or REQUEST_CHANGES
    Returns the review ID.
    """
    url = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"

    payload = {"body": body, "event": event}

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.post(url, headers=_get_headers(), json=payload)
        response.raise_for_status()
        data = response.json()

    review_id = data.get("id")
    logger.info(f"Posted review {review_id} to PR #{pr_number}")
    return review_id


async def verify_token() -> dict:
    """Verify GitHub token is valid and return user info."""
    url = f"{GITHUB_API_BASE}/user"

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, headers=_get_headers())
        response.raise_for_status()
        return response.json()
