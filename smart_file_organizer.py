#!/usr/bin/env python3
"""
Smart File Organizer AI
A production-grade file organization system using AI to analyze, tag, and organize files.
"""

import os
import sys
import json
import hashlib
import sqlite3
import argparse
import mimetypes
import threading
import time
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

# Third-party imports
try:
    import google.generativeai as genai
except ImportError:
    genai = None

try:
    import ollama
except ImportError:
    ollama = None

try:
    from PIL import Image
    import pillow_heif
except ImportError:
    Image = None
    pillow_heif = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

# Configuration loading
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        tomllib = None


@dataclass
class Config:
    """Configuration for Smart File Organizer AI"""
    # AI Model Configuration
    model: str = "gemini-2.0-flash-exp"
    ollama_model: str = "llama3.2-vision"
    gemini_api_key: Optional[str] = None
    use_local: bool = False
    
    # Processing Configuration
    max_workers: int = 4
    rate_limit_delay: float = 1.0
    
    # Cache Configuration
    cache_enabled: bool = True
    cache_path: str = "~/.config/smart-file-organizer/cache.db"
    cache_ttl_days: int = 30
    
    # Feature Flags
    rename_files: bool = False
    embed_metadata: bool = True
    create_json_sidecar: bool = True
    dry_run: bool = False
    interactive: bool = False
    
    # Organization Schema
    allowed_categories: List[str] = field(default_factory=lambda: [
        "document", "image", "video", "audio", "code", "archive", "other"
    ])
    
    allowed_tags: List[str] = field(default_factory=lambda: [
        "work", "personal", "important", "archive", "project", "reference"
    ])
    
    metadata_keys: List[str] = field(default_factory=lambda: [
        "title", "description", "category", "tags", "date", "author", "subject"
    ])


def load_config() -> Config:
    """Load configuration from TOML file and environment variables"""
    config = Config()
    
    # Try to load from TOML files
    config_paths = [
        Path.home() / ".config" / "smart-file-organizer" / "config.toml",
        Path.home() / ".smart-file-organizer.toml"
    ]
    
    if tomllib:
        for config_path in config_paths:
            if config_path.exists():
                try:
                    with open(config_path, "rb") as f:
                        toml_config = tomllib.load(f)
                        for key, value in toml_config.items():
                            if hasattr(config, key):
                                setattr(config, key, value)
                    print(f"✓ Loaded configuration from {config_path}")
                    break
                except Exception as e:
                    print(f"⚠ Error loading config from {config_path}: {e}")
    
    # Override with environment variables
    if os.getenv("GEMINI_API_KEY"):
        config.gemini_api_key = os.getenv("GEMINI_API_KEY")
    
    return config


class SmartHash:
    """Intelligent file hashing for efficient caching"""
    
    @staticmethod
    def calculate(file_path: Path, chunk_size: int = 65536) -> str:
        """
        Calculate smart hash: metadata + head (64KB) + tail (64KB)
        This is faster than hashing entire large files
        """
        hasher = hashlib.sha256()
        
        # Hash file metadata
        stat = file_path.stat()
        metadata = f"{file_path.name}|{stat.st_size}|{stat.st_mtime}"
        hasher.update(metadata.encode())
        
        # Hash head and tail of file
        file_size = stat.st_size
        
        with open(file_path, 'rb') as f:
            # Hash first 64KB
            head = f.read(chunk_size)
            hasher.update(head)
            
            # Hash last 64KB if file is large enough
            if file_size > chunk_size * 2:
                f.seek(-chunk_size, 2)
                tail = f.read(chunk_size)
                hasher.update(tail)
        
        return hasher.hexdigest()


class AnalysisCache:
    """Thread-safe SQLite cache for AI analysis results"""
    
    def __init__(self, cache_path: str, ttl_days: int = 30):
        self.cache_path = Path(cache_path).expanduser()
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        self.ttl_days = ttl_days
        self._local = threading.local()
        self._init_db()
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection"""
        if not hasattr(self._local, 'conn'):
            self._local.conn = sqlite3.connect(str(self.cache_path), check_same_thread=False)
        return self._local.conn
    
    def _init_db(self):
        """Initialize database schema"""
        conn = self._get_connection()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analysis_cache (
                file_hash TEXT,
                model TEXT,
                analysis TEXT,
                timestamp REAL,
                PRIMARY KEY (file_hash, model)
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON analysis_cache(timestamp)
        """)
        conn.commit()
    
    def get(self, file_hash: str, model: str) -> Optional[Dict]:
        """Retrieve cached analysis"""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT analysis FROM analysis_cache WHERE file_hash = ? AND model = ?",
            (file_hash, model)
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return None
    
    def set(self, file_hash: str, model: str, analysis: Dict):
        """Store analysis in cache"""
        conn = self._get_connection()
        conn.execute(
            "INSERT OR REPLACE INTO analysis_cache (file_hash, model, analysis, timestamp) VALUES (?, ?, ?, ?)",
            (file_hash, model, json.dumps(analysis), time.time())
        )
        conn.commit()
    
    def cleanup(self):
        """Remove entries older than TTL"""
        conn = self._get_connection()
        cutoff = time.time() - (self.ttl_days * 86400)
        conn.execute("DELETE FROM analysis_cache WHERE timestamp < ?", (cutoff,))
        conn.commit()
    
    def close(self):
        """Close database connection"""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()


class AIAnalyzer:
    """Multimodal AI analyzer supporting Gemini and Ollama"""
    
    def __init__(self, config: Config, cache: Optional[AnalysisCache] = None):
        self.config = config
        self.cache = cache
        
        # Initialize AI backend
        if not config.use_local and genai and config.gemini_api_key:
            genai.configure(api_key=config.gemini_api_key)
            self.backend = "gemini"
            self.model_name = config.model
        elif config.use_local and ollama:
            self.backend = "ollama"
            self.model_name = config.ollama_model
        else:
            raise RuntimeError("No AI backend available. Install google-generativeai or ollama.")
    
    def _prepare_prompt(self, file_path: Path, mime_type: str) -> str:
        """Prepare analysis prompt"""
        return f"""Analyze this file and extract structured metadata.

File: {file_path.name}
Type: {mime_type}

Please provide a JSON response with the following structure:
{{
    "title": "Brief descriptive title",
    "description": "Detailed description of content",
    "category": "One of: {', '.join(self.config.allowed_categories)}",
    "tags": ["relevant", "tags", "here"],
    "subject": "Main subject or topic",
    "date": "YYYY-MM-DD if date is mentioned or visible",
    "author": "Author/creator if identifiable",
    "suggested_filename": "descriptive_filename_without_extension"
}}

Analyze the actual content, not just the filename. Be specific and accurate."""
    
    def _analyze_with_gemini(self, file_path: Path, mime_type: str) -> Dict:
        """Analyze file using Google Gemini"""
        model = genai.GenerativeModel(self.model_name)
        
        prompt = self._prepare_prompt(file_path, mime_type)
        
        # Handle different file types
        if mime_type.startswith('image/'):
            # Upload image
            if Image:
                img = Image.open(file_path)
                response = model.generate_content([prompt, img])
            else:
                # Fallback to file upload
                uploaded_file = genai.upload_file(file_path)
                response = model.generate_content([prompt, uploaded_file])
        elif mime_type == 'application/pdf':
            # Upload PDF
            uploaded_file = genai.upload_file(file_path)
            response = model.generate_content([prompt, uploaded_file])
        else:
            # Text-based analysis
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)  # First 10KB
                response = model.generate_content(f"{prompt}\n\nContent preview:\n{content}")
            except:
                response = model.generate_content(prompt)
        
        # Parse JSON response
        text = response.text.strip()
        # Extract JSON from markdown code blocks if present
        if '```json' in text:
            text = text.split('```json')[1].split('```')[0].strip()
        elif '```' in text:
            text = text.split('```')[1].split('```')[0].strip()
        
        return json.loads(text)
    
    def _analyze_with_ollama(self, file_path: Path, mime_type: str) -> Dict:
        """Analyze file using Ollama"""
        prompt = self._prepare_prompt(file_path, mime_type)
        
        # Check if model supports vision
        model_info = ollama.show(self.model_name)
        supports_vision = 'vision' in str(model_info).lower()
        
        if mime_type.startswith('image/') and supports_vision:
            # Vision model analysis
            with open(file_path, 'rb') as f:
                import base64
                image_data = base64.b64encode(f.read()).decode()
            
            response = ollama.generate(
                model=self.model_name,
                prompt=prompt,
                images=[image_data],
                format='json'
            )
        else:
            # Text-based analysis
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read(10000)
                full_prompt = f"{prompt}\n\nContent preview:\n{content}"
            except:
                full_prompt = prompt
            
            response = ollama.generate(
                model=self.model_name,
                prompt=full_prompt,
                format='json'
            )
        
        return json.loads(response['response'])
    
    def analyze(self, file_path: Path) -> Dict:
        """Analyze file and return structured metadata"""
        # Calculate file hash
        file_hash = SmartHash.calculate(file_path)
        
        # Check cache
        if self.cache:
            cached = self.cache.get(file_hash, self.model_name)
            if cached:
                print(f"  ✓ Using cached analysis")
                return cached
        
        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        print(f"  🤖 Analyzing with {self.backend}...")
        
        # Perform analysis
        try:
            if self.backend == "gemini":
                result = self._analyze_with_gemini(file_path, mime_type)
            else:
                result = self._analyze_with_ollama(file_path, mime_type)
            
            # Add metadata
            result['mime_type'] = mime_type
            result['file_hash'] = file_hash
            result['analyzed_at'] = datetime.now().isoformat()
            result['model'] = self.model_name
            
            # Cache result
            if self.cache:
                self.cache.set(file_hash, self.model_name, result)
            
            return result
        
        except Exception as e:
            print(f"  ✗ Analysis failed: {e}")
            # Return minimal metadata
            return {
                'title': file_path.stem,
                'description': f'Error analyzing file: {str(e)}',
                'category': 'other',
                'tags': [],
                'mime_type': mime_type,
                'file_hash': file_hash,
                'analyzed_at': datetime.now().isoformat(),
                'model': self.model_name,
                'error': str(e)
            }


class MetadataManager:
    """Manage file metadata embedding and extraction"""
    
    @staticmethod
    def embed_metadata(file_path: Path, metadata: Dict) -> bool:
        """Embed metadata into file using exiftool (if available)"""
        try:
            import subprocess
            
            # Check if exiftool is available
            result = subprocess.run(['exiftool', '-ver'], capture_output=True)
            if result.returncode != 0:
                return False
            
            # Prepare exiftool arguments
            args = ['exiftool', '-overwrite_original']
            
            if 'title' in metadata:
                args.extend([f'-Title={metadata["title"]}'])
            if 'description' in metadata:
                args.extend([f'-Description={metadata["description"]}'])
            if 'tags' in metadata and metadata['tags']:
                tags_str = ', '.join(metadata['tags'])
                args.extend([f'-Keywords={tags_str}'])
            if 'author' in metadata:
                args.extend([f'-Author={metadata["author"]}'])
            if 'subject' in metadata:
                args.extend([f'-Subject={metadata["subject"]}'])
            
            args.append(str(file_path))
            
            result = subprocess.run(args, capture_output=True, text=True)
            return result.returncode == 0
        
        except Exception as e:
            print(f"  ⚠ Metadata embedding failed: {e}")
            return False
    
    @staticmethod
    def create_json_sidecar(file_path: Path, metadata: Dict):
        """Create JSON sidecar file with metadata"""
        sidecar_path = file_path.with_suffix(file_path.suffix + '.json')
        with open(sidecar_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        print(f"  ✓ Created sidecar: {sidecar_path.name}")


class FileOrganizer:
    """Main file organization orchestrator"""
    
    def __init__(self, config: Config):
        self.config = config
        self.cache = AnalysisCache(config.cache_path, config.cache_ttl_days) if config.cache_enabled else None
        self.analyzer = AIAnalyzer(config, self.cache)
    
    def safe_rename(self, file_path: Path, suggested_name: str) -> Optional[Path]:
        """Safely rename file with collision detection"""
        if not suggested_name:
            return None
        
        # Sanitize filename
        suggested_name = re.sub(r'[<>:"/\\|?*]', '_', suggested_name)
        suggested_name = suggested_name.strip()
        
        # Add original extension
        new_path = file_path.parent / f"{suggested_name}{file_path.suffix}"
        
        # Handle collisions
        counter = 1
        while new_path.exists() and new_path != file_path:
            new_path = file_path.parent / f"{suggested_name}_{counter}{file_path.suffix}"
            counter += 1
        
        if new_path == file_path:
            return None
        
        if not self.config.dry_run:
            file_path.rename(new_path)
            print(f"  ✓ Renamed: {file_path.name} → {new_path.name}")
        else:
            print(f"  [DRY RUN] Would rename: {file_path.name} → {new_path.name}")
        
        return new_path
    
    def process_file(self, file_path: Path) -> Dict:
        """Process a single file"""
        print(f"\n📄 Processing: {file_path}")
        
        result = {
            'file': str(file_path),
            'success': False,
            'metadata': None,
            'renamed_to': None
        }
        
        try:
            # Analyze file
            metadata = self.analyzer.analyze(file_path)
            result['metadata'] = metadata
            
            # Interactive mode
            if self.config.interactive:
                print(f"\n  Analysis results:")
                print(f"  Title: {metadata.get('title', 'N/A')}")
                print(f"  Category: {metadata.get('category', 'N/A')}")
                print(f"  Tags: {', '.join(metadata.get('tags', []))}")
                print(f"  Description: {metadata.get('description', 'N/A')[:100]}...")
                
                response = input("\n  Apply changes? [Y/n]: ").strip().lower()
                if response and response != 'y':
                    print("  ⊘ Skipped")
                    return result
            
            # Rename file
            if self.config.rename_files and 'suggested_filename' in metadata:
                new_path = self.safe_rename(file_path, metadata['suggested_filename'])
                if new_path:
                    result['renamed_to'] = str(new_path)
                    file_path = new_path
            
            # Embed metadata
            if self.config.embed_metadata and not self.config.dry_run:
                if MetadataManager.embed_metadata(file_path, metadata):
                    print(f"  ✓ Embedded metadata")
            
            # Create JSON sidecar
            if self.config.create_json_sidecar and not self.config.dry_run:
                MetadataManager.create_json_sidecar(file_path, metadata)
            
            result['success'] = True
            print(f"  ✅ Completed")
        
        except Exception as e:
            print(f"  ✗ Error: {e}")
            result['error'] = str(e)
        
        return result
    
    def process_batch(self, paths: List[Path]) -> List[Dict]:
        """Process multiple files concurrently"""
        results = []
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers) as executor:
            futures = {executor.submit(self.process_file, path): path for path in paths}
            
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results.append(result)
                    
                    # Rate limiting
                    if self.config.rate_limit_delay > 0:
                        time.sleep(self.config.rate_limit_delay)
                
                except Exception as e:
                    path = futures[future]
                    print(f"✗ Failed to process {path}: {e}")
                    results.append({
                        'file': str(path),
                        'success': False,
                        'error': str(e)
                    })
        
        return results
    
    def cleanup(self):
        """Cleanup resources"""
        if self.cache:
            self.cache.cleanup()
            self.cache.close()


def collect_files(path: Path, recursive: bool = False) -> List[Path]:
    """Collect files to process"""
    if path.is_file():
        return [path]
    
    files = []
    pattern = "**/*" if recursive else "*"
    
    for item in path.glob(pattern):
        if item.is_file() and not item.name.startswith('.'):
            files.append(item)
    
    return files


def create_parser() -> argparse.ArgumentParser:
    """Create command-line argument parser"""
    parser = argparse.ArgumentParser(
        description="Smart File Organizer AI - Intelligent file organization using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Analyze and organize a single file
  python smart_file_organizer.py document.pdf --rename --embed-metadata
  
  # Batch process a directory
  python smart_file_organizer.py ./photos --batch --recursive --rename
  
  # Dry run to preview changes
  python smart_file_organizer.py ./documents --batch --dry-run
  
  # Interactive mode with manual review
  python smart_file_organizer.py ./files --batch --interactive
  
  # Use local Ollama instead of Gemini
  python smart_file_organizer.py image.jpg --local --rename
        """
    )
    
    parser.add_argument('path', type=str, help='File or directory to process')
    parser.add_argument('--batch', '-b', action='store_true', help='Batch process directory')
    parser.add_argument('--recursive', '-R', action='store_true', help='Process directories recursively')
    parser.add_argument('--rename', '-r', action='store_true', help='Rename files based on content')
    parser.add_argument('--embed-metadata', '-x', action='store_true', default=True, help='Embed metadata into files')
    parser.add_argument('--no-sidecar', action='store_true', help='Do not create JSON sidecar files')
    parser.add_argument('--local', '-l', action='store_true', help='Use local Ollama instead of Gemini')
    parser.add_argument('--dry-run', '-n', action='store_true', help='Preview changes without applying')
    parser.add_argument('--interactive', '-i', action='store_true', help='Interactive mode with manual review')
    parser.add_argument('--workers', '-w', type=int, default=4, help='Number of concurrent workers')
    parser.add_argument('--model', '-m', type=str, help='AI model to use')
    parser.add_argument('--no-cache', action='store_true', help='Disable caching')
    
    return parser


def main():
    """Main entry point"""
    parser = create_parser()
    args = parser.parse_args()
    
    # Load configuration
    config = load_config()
    
    # Override with command-line arguments
    if args.local:
        config.use_local = True
    if args.rename:
        config.rename_files = True
    if args.embed_metadata:
        config.embed_metadata = True
    if args.no_sidecar:
        config.create_json_sidecar = False
    if args.dry_run:
        config.dry_run = True
    if args.interactive:
        config.interactive = True
    if args.workers:
        config.max_workers = args.workers
    if args.model:
        if config.use_local:
            config.ollama_model = args.model
        else:
            config.model = args.model
    if args.no_cache:
        config.cache_enabled = False
    
    # Validate path
    path = Path(args.path).resolve()
    if not path.exists():
        print(f"✗ Error: Path does not exist: {path}")
        sys.exit(1)
    
    # Print configuration
    print("=" * 60)
    print("Smart File Organizer AI")
    print("=" * 60)
    print(f"Backend: {'Ollama (Local)' if config.use_local else 'Google Gemini'}")
    print(f"Model: {config.ollama_model if config.use_local else config.model}")
    print(f"Mode: {'Dry Run' if config.dry_run else 'Active'}")
    print(f"Workers: {config.max_workers}")
    print(f"Cache: {'Enabled' if config.cache_enabled else 'Disabled'}")
    print("=" * 60)
    
    # Collect files
    if args.batch:
        files = collect_files(path, args.recursive)
        print(f"\n📁 Found {len(files)} files to process")
    else:
        if path.is_dir():
            print("✗ Error: Path is a directory. Use --batch to process directories.")
            sys.exit(1)
        files = [path]
    
    if not files:
        print("✗ No files to process")
        sys.exit(0)
    
    # Process files
    organizer = FileOrganizer(config)
    
    try:
        start_time = time.time()
        
        if len(files) == 1:
            results = [organizer.process_file(files[0])]
        else:
            results = organizer.process_batch(files)
        
        elapsed = time.time() - start_time
        
        # Print summary
        print("\n" + "=" * 60)
        print("Summary")
        print("=" * 60)
        successful = sum(1 for r in results if r['success'])
        failed = len(results) - successful
        print(f"Total: {len(results)} files")
        print(f"Success: {successful}")
        print(f"Failed: {failed}")
        print(f"Time: {elapsed:.2f}s")
        print("=" * 60)
        
        # Save results
        if not config.dry_run:
            results_file = Path.cwd() / f"organizer_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(results_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            print(f"\n📊 Results saved to: {results_file}")
    
    finally:
        organizer.cleanup()


if __name__ == "__main__":
    main()
