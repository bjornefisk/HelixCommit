from pathlib import Path

import git

from helixcommit.git_client import CommitRange, GitRepository


def create_commit(
    repo: git.Repo, base_path: Path, relative: str, content: str, message: str
) -> git.Commit:
    file_path = base_path / relative
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    repo.index.add([relative])
    actor = git.Actor("Test User", "test@example.com")
    return repo.index.commit(message, author=actor, committer=actor)


def test_git_repository_iter_commits_and_tags(tmp_path):
    repo = git.Repo.init(tmp_path)
    first_commit = create_commit(
        repo, Path(tmp_path), "README.md", "Initial", "chore: initial commit"
    )
    repo.create_tag("v0.1.0", ref=first_commit)

    second_commit = create_commit(
        repo, Path(tmp_path), "app.py", "print('hi')\n", "feat: add app entrypoint"
    )
    repo.create_tag("v0.2.0", ref=second_commit)

    git_repo = GitRepository(tmp_path)
    tags = git_repo.list_tags()
    assert [tag.name for tag in tags] == ["v0.2.0", "v0.1.0"]

    commit_range = CommitRange(since="v0.1.0", until="HEAD", include_merges=False)
    commits = list(git_repo.iter_commits(commit_range))

    assert len(commits) == 1
    commit = commits[0]
    assert commit.subject == "feat: add app entrypoint"
    assert commit.author_name == "Test User"
    assert commit.sha == second_commit.hexsha


def test_git_repository_include_diffs(tmp_path):
    repo = git.Repo.init(tmp_path)
    create_commit(
        repo, Path(tmp_path), "README.md", "Initial", "chore: initial commit"
    )

    # Change file content to generate diff
    create_commit(
        repo, Path(tmp_path), "README.md", "Initial\nUpdated", "feat: update readme"
    )

    git_repo = GitRepository(tmp_path)
    commit_range = CommitRange(max_count=1)

    # Test without diffs
    commits = list(git_repo.iter_commits(commit_range, include_diffs=False))
    assert len(commits) == 1
    assert commits[0].diff is None

    # Test with diffs
    commits = list(git_repo.iter_commits(commit_range, include_diffs=True))
    assert len(commits) == 1
    assert commits[0].diff is not None
    assert "Updated" in commits[0].diff


def test_git_repository_paths_filter(tmp_path):
    repo = git.Repo.init(tmp_path)
    create_commit(
        repo, Path(tmp_path), "README.md", "Initial", "chore: initial commit"
    )
    second = create_commit(
        repo, Path(tmp_path), "feature.txt", "Feature", "feat: add feature"
    )
    create_commit(
        repo, Path(tmp_path), "docs.txt", "Docs", "docs: add docs"
    )

    git_repo = GitRepository(tmp_path)
    commit_range = CommitRange(paths=("feature.txt",))
    commits = list(git_repo.iter_commits(commit_range))

    assert len(commits) == 1
    assert commits[0].sha == second.hexsha


def test_git_repository_collects_files(tmp_path):
    repo = git.Repo.init(tmp_path)
    create_commit(
        repo, Path(tmp_path), "src/app.py", "print('hi')\n", "feat: add app"
    )

    git_repo = GitRepository(tmp_path)
    commit_range = CommitRange(max_count=1)
    commits = list(git_repo.iter_commits(commit_range, include_files=True))

    assert commits
    assert commits[0].files == ["src/app.py"]


def test_get_gitlab_slug_https(tmp_path):
    """Test GitLab slug extraction from HTTPS URL."""
    repo = git.Repo.init(tmp_path)
    repo.create_remote("origin", "https://gitlab.com/mygroup/myproject.git")

    git_repo = GitRepository(tmp_path)
    slug = git_repo.get_gitlab_slug()

    assert slug == "mygroup/myproject"


def test_get_gitlab_slug_ssh(tmp_path):
    """Test GitLab slug extraction from SSH URL."""
    repo = git.Repo.init(tmp_path)
    repo.create_remote("origin", "git@gitlab.com:mygroup/myproject.git")

    git_repo = GitRepository(tmp_path)
    slug = git_repo.get_gitlab_slug()

    assert slug == "mygroup/myproject"


def test_get_gitlab_slug_subgroups(tmp_path):
    """Test GitLab slug extraction with subgroups."""
    repo = git.Repo.init(tmp_path)
    repo.create_remote("origin", "git@gitlab.com:group/subgroup/project.git")

    git_repo = GitRepository(tmp_path)
    slug = git_repo.get_gitlab_slug()

    assert slug == "group/subgroup/project"


def test_get_gitlab_slug_self_hosted(tmp_path):
    """Test GitLab slug extraction from self-hosted instance."""
    repo = git.Repo.init(tmp_path)
    repo.create_remote("origin", "git@gitlab.example.com:team/project.git")

    git_repo = GitRepository(tmp_path)
    slug = git_repo.get_gitlab_slug()

    assert slug == "team/project"


def test_get_gitlab_slug_returns_none_for_github(tmp_path):
    """Test that GitHub URLs don't match GitLab pattern."""
    repo = git.Repo.init(tmp_path)
    repo.create_remote("origin", "git@github.com:owner/repo.git")

    git_repo = GitRepository(tmp_path)
    slug = git_repo.get_gitlab_slug()

    assert slug is None


def test_get_github_slug_returns_none_for_gitlab(tmp_path):
    """Test that GitLab URLs don't match GitHub pattern."""
    repo = git.Repo.init(tmp_path)
    repo.create_remote("origin", "git@gitlab.com:mygroup/myproject.git")

    git_repo = GitRepository(tmp_path)
    slug = git_repo.get_github_slug()

    assert slug is None
