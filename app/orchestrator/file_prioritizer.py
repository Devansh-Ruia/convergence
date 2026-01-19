import re
from typing import List
from app.models.session import FileChange


def prioritize_files(files: List[FileChange]) -> List[FileChange]:
    """
    Sort files by review priority:
    1. Security-sensitive (auth, crypto, input handling)
    2. Core business logic
    3. API endpoints / controllers
    4. Database / repositories
    5. Tests (lower priority)
    6. Config / static (lowest)
    """
    
    def get_priority_score(file: FileChange) -> int:
        """Get priority score for a file (lower = higher priority)."""
        path = file.path.lower()
        
        # Security-sensitive files (highest priority)
        security_patterns = [
            r'auth', r'login', r'password', r'token', r'jwt', r'session',
            r'crypto', r'encrypt', r'decrypt', r'hash', r'secret',
            r'input', r'validation', r'sanitize', r'escape', r'csrf',
            r'permission', r'role', r'access', r'security'
        ]
        
        for pattern in security_patterns:
            if re.search(pattern, path):
                return 1
        
        # Core business logic
        business_patterns = [
            r'service', r'business', r'logic', r'domain', r'core',
            r'model', r'entity', r'aggregate', r'use.case'
        ]
        
        for pattern in business_patterns:
            if re.search(pattern, path):
                return 2
        
        # API endpoints / controllers
        api_patterns = [
            r'controller', r'endpoint', r'route', r'handler', r'api',
            r'rest', r'graphql', r'view', r'servlet'
        ]
        
        for pattern in api_patterns:
            if re.search(pattern, path):
                return 3
        
        # Database / repositories
        db_patterns = [
            r'repository', r'dao', r'db', r'database', r'query',
            r'migration', r'schema', r'orm', r'sql'
        ]
        
        for pattern in db_patterns:
            if re.search(pattern, path):
                return 4
        
        # Tests (lower priority)
        test_patterns = [
            r'test', r'spec', r'fixture', r'mock', r'stub'
        ]
        
        for pattern in test_patterns:
            if re.search(pattern, path):
                return 5
        
        # Config / static (lowest priority)
        config_patterns = [
            r'config', r'setting', r'env', r'constant', r'static',
            r'asset', r'public', r'resource', r'locale'
        ]
        
        for pattern in config_patterns:
            if re.search(pattern, path):
                return 6
        
        # Default priority
        return 3
    
    # Sort by priority score, then by file size (larger changes first)
    sorted_files = sorted(
        files,
        key=lambda f: (get_priority_score(f), -(f.additions + f.deletions))
    )
    
    return sorted_files


def chunk_files_for_context(files: List[FileChange], max_tokens: int = 8000) -> List[List[FileChange]]:
    """
    Split files into chunks that fit context window.
    Keep related files together when possible.
    """
    if not files:
        return []
    
    # Estimate tokens per file (rough approximation: 1 token ≈ 4 chars)
    def estimate_tokens(file: FileChange) -> int:
        # Count characters in patch plus overhead for metadata
        patch_length = len(file.patch or "")
        metadata_overhead = 200  # Approximate metadata per file
        return (patch_length + metadata_overhead) // 4
    
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for file in files:
        file_tokens = estimate_tokens(file)
        
        # If single file exceeds max_tokens, put it in its own chunk
        if file_tokens > max_tokens:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0
            chunks.append([file])
            continue
        
        # If adding this file would exceed limit, start new chunk
        if current_tokens + file_tokens > max_tokens and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_tokens = 0
        
        current_chunk.append(file)
        current_tokens += file_tokens
    
    # Add final chunk if not empty
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def should_chunk_pr(files: List[FileChange]) -> bool:
    """
    Determine if a PR should be chunked for processing.
    """
    total_files = len(files)
    total_changes = sum(f.additions + f.deletions for f in files)
    
    # Chunk if more than 10 files or more than 15k characters of changes
    return total_files > 10 or total_changes > 15000


def get_file_summary(files: List[FileChange]) -> str:
    """Get a summary of files for logging/debugging."""
    if not files:
        return "No files"
    
    summary = f"{len(files)} files: "
    file_names = [f.path.split('/')[-1] for f in files[:5]]
    if len(files) > 5:
        summary += f"{', '.join(file_names)} ... (+{len(files)-5} more)"
    else:
        summary += ", ".join(file_names)
    
    return summary
