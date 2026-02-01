# Podcast-to-Text

Automated podcast transcription tool - fetches RSS feeds and transcribes audio using Azure Speech Services Batch API.

## Features

- 🎙️ Multi-channel podcast subscriptions
- 🔄 Async processing with batch submission
- 🗣️ Azure Batch Transcription API (no local audio download)
- 📁 Structured output (Markdown + JSON)
- 💾 SQLite state tracking
- 🔧 CLI and config file modes

## Architecture

```
submit.py  -->  Azure Batch API  -->  query.py
   |                                      |
   v                                      v
pending_episodes (DB)            processed_episodes (DB)
                                         |
                                         v
                                   output/{channel}/
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Azure Speech credentials
```

### 3. Submit Transcription

```bash
# Single RSS feed (auto-detect channel name)
python src/submit.py https://example.com/podcast-feed.xml

# With custom channel name and language
python src/submit.py https://example.com/feed.xml --name my-podcast --lang zh-CN

# Batch mode from config file
python src/submit.py --config
```

### 4. Query Results

```bash
# Check all pending tasks
python src/query.py

# Filter by channel
python src/query.py --channel nopriors

# List pending tasks only
python src/query.py --list
```

## Usage

### submit.py - Submit Tasks

| Argument | Description |
|----------|-------------|
| `url` | RSS feed URL (positional) |
| `--name, -n` | Channel name (auto-detected if not specified) |
| `--lang, -l` | Language code (default: auto). Use `auto` for automatic detection, or specify like `en-US`, `zh-CN` |
| `--config, -c` | Read from config/channels.yaml |

### query.py - Query Results

| Argument | Description |
|----------|-------------|
| `--channel, -c` | Filter by channel name |
| `--list, -l` | List pending tasks without processing |

## Configuration

### channels.txt (for batch mode)

Simple format - one RSS URL per line:

```
# Lines starting with # are comments
https://example.com/podcast1/feed.xml
https://example.com/podcast2/feed.xml
https://example.com/podcast3/feed.xml
```

### Environment Variables

| Variable | Description |
|----------|-------------|
| AZURE_SPEECH_KEY | Azure Speech service subscription key |
| AZURE_SPEECH_REGION | Azure region (e.g., southeastasia, eastus) |

## Output Format

### Directory Structure

```
output/
├── nopriors/
│   └── 2024-01-29/
│       ├── episode-title.md
│       └── episode-title.json
└── another-podcast/
    └── ...
```

### Markdown Output

```markdown
# Episode Title

- Published: 2024-01-29
- Duration: 45:30
- Source: nopriors

## Transcript

[00:00:00] This is the transcribed text content...

[00:00:15] Next segment of transcription...
```

### JSON Output

```json
{
  "title": "Episode Title",
  "published": "2024-01-29T10:00:00",
  "duration": "45:30",
  "channel": "nopriors",
  "transcript": [
    {"time": "00:00:00", "start": 0.0, "end": 5.2, "text": "..."}
  ],
  "processed_at": "2024-01-30T08:15:00"
}
```

## Workflow Example

```bash
# Submit multiple podcasts
python src/submit.py https://example.com/podcast-feed.xml
python src/submit.py https://example.com/tech-podcast.xml --name tech-pod

# Check status periodically
python src/query.py --list

# Download completed results
python src/query.py
```

### Cron Schedule

```bash
# Submit new episodes every hour
0 * * * * cd /path/to/podcast-to-text && python src/submit.py --config

# Query results every 30 minutes
*/30 * * * * cd /path/to/podcast-to-text && python src/query.py
```

## Requirements

- Python 3.10+
- Azure Speech Services subscription

## Azure Setup

### Create Azure Speech Service

You need an Azure Cognitive Services resource with Speech capabilities.

```bash
# Login to Azure
az login

# Set subscription
az account set --subscription <your-subscription-id>

# Create resource group (if needed)
az group create --name rg-podcast --location eastus

# Create Speech Service (S0 tier for batch transcription)
az cognitiveservices account create \
  --name podcast-speech-service \
  --resource-group rg-podcast \
  --kind SpeechServices \
  --sku S0 \
  --location eastus \
  --yes

# Get the API key
az cognitiveservices account keys list \
  --name podcast-speech-service \
  --resource-group rg-podcast \
  --query "key1" -o tsv
```

### Alternative: Use AIServices (Multi-service)

```bash
az cognitiveservices account create \
  --name podcast-ai-service \
  --resource-group rg-podcast \
  --kind AIServices \
  --sku S0 \
  --location eastus \
  --yes
```

### Configure Environment

After creating the resource, set up your `.env` file:

```bash
# Copy template
cp .env.example .env

# Edit with your values
AZURE_SPEECH_KEY=<key-from-above-command>
AZURE_SPEECH_REGION=eastus  # must match your resource location
```

### Supported Regions

Common regions for Speech Services:
- `eastus`, `eastus2`, `westus`, `westus2`
- `southeastasia`, `eastasia`
- `westeurope`, `northeurope`
- `australiaeast`

### Pricing Notes

- **S0 tier** is required for Batch Transcription API
- Free tier (F0) does not support batch transcription
- Batch transcription is billed per audio hour processed
- See [Azure Speech pricing](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/)

## License

Apache License 2.0 - See [LICENSE](LICENSE) file for details.
