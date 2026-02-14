# Installation Guide - Smart File Organizer AI

## Quick Start (Windows)

### 1. Prerequisites
- Python 3.10 or higher
- Git (optional, for cloning)
- Google Gemini API key OR Ollama installed

### 2. Installation Steps

#### Option A: Using Git
```powershell
# Clone the repository
git clone https://github.com/YOUR_USERNAME/smart-file-organizer-ai.git
cd smart-file-organizer-ai

# Install dependencies
pip install -r requirements.txt
```

#### Option B: Manual Download
1. Download the ZIP file from GitHub
2. Extract to your desired location
3. Open PowerShell in the extracted folder
4. Run: `pip install -r requirements.txt`

### 3. Configuration

#### For Google Gemini (Cloud AI)
```powershell
# Set API key as environment variable
$env:GEMINI_API_KEY="your-api-key-here"

# Or create config file
mkdir "$env:USERPROFILE\.config\smart-file-organizer"
Copy-Item config.example.toml "$env:USERPROFILE\.config\smart-file-organizer\config.toml"
# Edit config.toml and add your API key
```

#### For Ollama (Local AI)
```powershell
# Install Ollama from https://ollama.ai/
# Download and install the Windows version

# Pull a vision model
ollama pull llama3.2-vision

# Or use another model
ollama pull llava
```

### 4. Optional: Install ExifTool
For metadata embedding into files:
1. Download from: https://exiftool.org/
2. Extract `exiftool(-k).exe` to a folder
3. Rename to `exiftool.exe`
4. Add folder to PATH or place in project directory

### 5. Verify Installation
```powershell
# Test the CLI
python smart_file_organizer.py --help

# Test with a file (dry run)
python smart_file_organizer.py test_document.txt --dry-run
```

## Usage

### Command Line Interface

#### Basic Usage
```powershell
# Analyze a single file
python smart_file_organizer.py document.pdf

# Rename file based on content
python smart_file_organizer.py photo.jpg --rename

# Batch process directory
python smart_file_organizer.py C:\Users\YourName\Documents --batch --rename
```

#### Advanced Options
```powershell
# Recursive processing
python smart_file_organizer.py C:\Photos --batch --recursive --rename --embed-metadata

# Dry run (preview only)
python smart_file_organizer.py C:\Files --batch --dry-run

# Interactive mode
python smart_file_organizer.py C:\Documents --batch --interactive

# Use local Ollama
python smart_file_organizer.py image.jpg --local --rename

# Custom number of workers
python smart_file_organizer.py C:\Files --batch --workers 8

# Disable caching
python smart_file_organizer.py file.pdf --no-cache
```

### Web Interface

#### Start the Web Server
```powershell
python web_server.py
```

Then open your browser to: http://localhost:5000

#### Features
- Drag and drop files
- Choose AI model (Gemini or Ollama)
- Configure processing options
- View results in real-time
- Beautiful, modern interface

## Troubleshooting

### "No AI backend available"
**Solution:**
```powershell
# Install Gemini support
pip install google-generativeai

# OR install Ollama support
pip install ollama
```

### "GEMINI_API_KEY not found"
**Solution:**
```powershell
# Set environment variable
$env:GEMINI_API_KEY="your-key-here"

# Make it permanent (PowerShell)
[System.Environment]::SetEnvironmentVariable('GEMINI_API_KEY', 'your-key-here', 'User')
```

### "ExifTool not found"
**Solution:**
- Download from https://exiftool.org/
- Add to PATH or place in project directory
- Or disable metadata embedding: `--no-embed-metadata`

### "Module not found" errors
**Solution:**
```powershell
# Reinstall all dependencies
pip install -r requirements.txt --upgrade
```

### Slow processing
**Solutions:**
- Increase workers: `--workers 8`
- Use local Ollama: `--local`
- Enable caching (enabled by default)
- Process smaller batches

### Out of memory
**Solutions:**
- Reduce workers: `--workers 2`
- Process files in smaller batches
- Close other applications

## Performance Tips

1. **Use Caching**: Enabled by default, saves ~80% API calls on re-runs
2. **Adjust Workers**: Default is 4, increase for faster processing
3. **Local AI**: Use Ollama for unlimited, free processing
4. **Batch Processing**: Process multiple files at once for efficiency

## Next Steps

1. **Test with sample files**: Try different file types
2. **Configure settings**: Customize in `config.toml`
3. **Set up automation**: Create batch scripts for regular tasks
4. **Explore features**: Try interactive mode, dry runs, etc.

## Getting Help

- Check the main README.md for detailed documentation
- Open an issue on GitHub for bugs
- Review example configurations in `config.example.toml`

---

**Happy Organizing! 🚀**
