# MCP Server Configuration

This document describes the configured MCP (Model Context Protocol) servers for the MyPhotos project.

## Currently Active MCP Servers

### 1. Context7 MCP
- **Purpose**: Documentation lookup and library ID resolution
- **Status**: ✅ Active
- **API Key**: Configured

### 2. Filesystem MCP
- **Purpose**: File system operations within allowed directories
- **Status**: ✅ Active
- **Allowed Path**: `/Users/akshay/Desktop/code/myphotos`
- **Capabilities**: Read/write files, list directories, search files

### 3. Browser Tools MCP
- **Purpose**: Browser automation and testing
- **Status**: ✅ Active
- **Capabilities**: Screenshots, console logs, accessibility audits

### 4. Sequential Thinking MCP
- **Purpose**: Structured problem-solving and reasoning
- **Status**: ✅ Active
- **Capabilities**: Multi-step thinking, planning, analysis

### 5. Git MCP
- **Purpose**: Git repository operations
- **Status**: ✅ Active
- **Repository**: `/Users/akshay/Desktop/code/myphotos`
- **Capabilities**: Status, diff, commit, branch operations

### 6. Magic MCP (21st.dev)
- **Purpose**: UI component generation and inspiration
- **Status**: ✅ Active
- **API Key**: Configured
- **Capabilities**: Component builder, logo search, UI refinement

### 7. Fetch MCP
- **Purpose**: Web content fetching
- **Status**: ✅ Active
- **Capabilities**: Fetch HTML, Markdown, JSON, YouTube transcripts

### 8. GitHub MCP Server
- **Purpose**: GitHub API operations
- **Status**: ✅ Active
- **Token**: Configured
- **Capabilities**: Issues, PRs, repos, code search

### 9. Memory MCP
- **Purpose**: Knowledge graph and entity management
- **Status**: ✅ Active
- **Capabilities**: Create entities, relations, observations

### 10. Markdownify MCP
- **Purpose**: Convert files to markdown
- **Status**: ✅ Active
- **Path**: `/Users/akshay/Documents/Cline/MCP/markdownify-mcp/dist/index.js`
- **Capabilities**: PDF, DOCX, PPTX, XLSX, audio, image to markdown

### 11. Redis MCP
- **Purpose**: Redis database operations
- **Status**: ✅ Active
- **Connection**: `redis://localhost:6379`
- **Capabilities**: Get, set, delete, list keys
- **Verified**: Successfully tested with Celery task metadata

## Not Available / Removed

### SQLite MCP
- **Status**: ❌ Not Available
- **Reason**: No official `@modelcontextprotocol/server-sqlite` package exists
- **Alternative**: Use the filesystem MCP to read SQLite database files directly, or use Python's sqlite3 module in backend code

## Usage Examples

### Reading the README file
```javascript
// Using filesystem MCP
read_text_file("/Users/akshay/Desktop/code/myphotos/README.md")

// Using markdownify MCP
get-markdown-file("/Users/akshay/Desktop/code/myphotos/README.md")
```

### Querying Redis
```javascript
// List all keys
list({ pattern: "*" })

// Get a specific key
get({ key: "celery-task-meta-..." })

// Set a value
set({ key: "mykey", value: "myvalue" })
```

### Git Operations
```javascript
// Check git status
git_status({ repo_path: "/Users/akshay/Desktop/code/myphotos" })

// View recent commits
git_log({ repo_path: "/Users/akshay/Desktop/code/myphotos", max_count: 10 })
```

## Configuration File Location

```
/Users/akshay/Desktop/code/myphotos/../../../Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json
```

## Notes

- All MCP servers are configured with `"disabled": false` and `"autoApprove": []`
- Redis server requires Redis to be running on `localhost:6379`
- Filesystem MCP is restricted to the project directory for security
- Some MCP servers require API keys or tokens (Context7, Magic, GitHub)

## Troubleshooting

### Redis MCP not connecting
- Ensure Redis is running: `brew services start redis` (macOS)
- Check Redis status: `redis-cli ping` (should return PONG)

### SQLite access
- No dedicated SQLite MCP server exists
- Use filesystem MCP to read `.db` files as text
- Use backend Python code for database operations

### MCP server not loading
- Check the MCP settings file for syntax errors
- Ensure the command/path for each server is correct
- Restart VS Code or the MCP client after configuration changes