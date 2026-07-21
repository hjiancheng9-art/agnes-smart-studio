
const vscode = require('vscode');
const path = require('path');
const { spawn } = require('child_process');
const readline = require('readline');

let bridgeProcess = null;
let bridgeRL = null;
let currentPanel = null;
let outputChannel = null;
let pendingRequests = new Map();
let isBridgeBusy = false;
let bridgeRestartCount = 0;
const MAX_RESTARTS = 10;

// ── Path resolution ────────────────────────────────────────

function getCruxRoot() {
    // 1) Hardcoded CRUX project root — always works regardless of workspace
    const cruxHome = 'C:/Users/huangjiancheng/agnes-smart-studio';
    const fs = require('fs');
    if (fs.existsSync(path.join(cruxHome, 'tools', 'crux_bridge.py'))) return cruxHome;
    // 2) Workspace root (if it happens to be the CRUX project)
    const ws = vscode.workspace.workspaceFolders;
    if (ws) {
        const candidate = ws[0].uri.fsPath;
        if (fs.existsSync(path.join(candidate, 'tools', 'crux_bridge.py'))) return candidate;
    }
    // 3) Walk up from extension dir
    let dir = __dirname;
    for (let i = 0; i < 15; i++) {
        if (fs.existsSync(path.join(dir, 'tools', 'crux_bridge.py'))) return dir;
        const parent = path.dirname(dir);
        if (parent === dir) break;
        dir = parent;
    }
    // 4) Last resort: workspace or extension fallback
    return ws ? ws[0].uri.fsPath : path.resolve(__dirname, '..');
}

function getWorkspaceRoot() {
    const ws = vscode.workspace.workspaceFolders;
    if (ws) return ws[0].uri.fsPath;
    return getCruxRoot();
}

function getPythonPath() {
    // Use system Python (has all CRUX dependencies). VS Code's Python extension
    // may point to a venv that lacks core modules.
    const sysPython = 'C:/Users/huangjiancheng/AppData/Local/Programs/Python/Python311/python.exe';
    const fs = require('fs');
    if (fs.existsSync(sysPython)) return sysPython;
    return vscode.workspace.getConfiguration('python').get('defaultInterpreterPath') || 'python';
}

function getBridgePath() {
    return path.join(getCruxRoot(), 'tools', 'crux_bridge.py');
}

function log(msg) {
    if (!outputChannel) {
        outputChannel = vscode.window.createOutputChannel('CRUX Agent');
    }
    outputChannel.appendLine(`[${new Date().toLocaleTimeString()}] ${msg}`);
}

// ── Active editor context ──────────────────────────────────

function getActiveEditorContext() {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return [];
    const doc = editor.document;
    if (doc.getText().length > 50000) return [];
    return [{
        path: vscode.workspace.asRelativePath(doc.uri),
        content: doc.getText(),
        languageId: doc.languageId
    }];
}

// ── Safe bridge write ──────────────────────────────────────

function writeToBridge(json) {
    if (!bridgeProcess || bridgeProcess.killed || !bridgeProcess.stdin || bridgeProcess.stdin.destroyed) {
        const err = new Error('Bridge not running — please reload VS Code window');
        log('writeToBridge failed: ' + err.message);
        throw err;
    }
    bridgeProcess.stdin.write(json);
}

// ── Bridge process management ──────────────────────────────

function startBridge() {
    return new Promise((resolve, reject) => {
        const pythonPath = getPythonPath();
        const bridgePath = getBridgePath();
        const cwd = getCruxRoot();  // bridge needs CRUX root for Python imports

        log(`Starting bridge: ${pythonPath} ${bridgePath}`);

        // Pipe stderr to a file so we can see Python tracebacks
        const fs = require('fs');
        const stderrLog = fs.createWriteStream(
            path.join(getCruxRoot(), 'bridge-crash.log'), { flags: 'a' }
        );
        stderrLog.write(`\n=== Bridge start ${new Date().toISOString()} ===\n`);
        stderrLog.write(`Python: ${pythonPath}\nScript: ${bridgePath}\nCWD: ${cwd}\n`);

        bridgeProcess = spawn(pythonPath, ['-u', bridgePath], {
            cwd,
            stdio: ['pipe', 'pipe', 'pipe'],
            env: { ...process.env, PYTHONUNBUFFERED: '1' }
        });

        bridgeProcess.stderr.pipe(stderrLog);
        bridgeProcess.on('exit', (code, signal) => {
            stderrLog.write(`[exit] code=${code} signal=${signal}\n`);
            stderrLog.end();
        });

        bridgeRL = readline.createInterface({ input: bridgeProcess.stdout });

        bridgeRL.on('line', (line) => {
            const trimmed = line.trim();
            if (!trimmed) return;
            try {
                const msg = JSON.parse(trimmed);
                const handler = pendingRequests.get(msg.id);
                if (handler && handler.onMessage) {
                    handler.onMessage(msg);
                }
                if (msg.type === 'done' && handler) {
                    pendingRequests.delete(msg.id);
                    handler.resolve();
                    isBridgeBusy = false;
                }
            } catch (e) { /* skip non-JSON */ }
        });

        bridgeProcess.stderr.on('data', (data) => {
            log(`[bridge] ${data.toString().trim()}`);
        });

        bridgeProcess.on('error', (err) => {
            const msg = `Bridge spawn error: ${err.message}\nPython: ${pythonPath}\nScript: ${bridgePath}\nCWD: ${cwd}`;
            log(msg);
            try { stderrLog.write(msg + '\n'); stderrLog.end(); } catch(e) {}
            reject(err);
        });

        bridgeProcess.on('close', (code) => {
            log(`Bridge exited with code ${code}`);
            bridgeRL.close();
            bridgeRL = null;
            bridgeProcess = null;
            for (const [id, handler] of pendingRequests) {
                handler.reject(new Error(`Bridge exited (code ${code})`));
            }
            pendingRequests.clear();
            isBridgeBusy = false;
        });

        setTimeout(() => {
            if (!bridgeProcess || bridgeProcess.killed) {
                reject(new Error('Bridge died during startup'));
            } else {
                bridgeRestartCount = 0;
                resolve();
            }
        }, 5000);
    });
}

async function ensureBridge() {
    if (bridgeProcess && !bridgeProcess.killed && bridgeProcess.stdin && !bridgeProcess.stdin.destroyed) return;
    if (bridgeRestartCount >= MAX_RESTARTS) {
        throw new Error('Bridge restart limit exceeded. Please reload VS Code window.');
    }
    bridgeRestartCount++;
    log(`Bridge restart ${bridgeRestartCount}/${MAX_RESTARTS}`);
    await startBridge();
    if (!bridgeProcess || bridgeProcess.killed) {
        throw new Error('Bridge failed to start');
    }
}

function quitBridge() {
    if (bridgeProcess && !bridgeProcess.killed) {
        try {
            writeToBridge(JSON.stringify({ id: 'quit', method: 'quit', params: {} }) + '\n');
        } catch (e) { /* already dead */ }
        setTimeout(() => {
            if (bridgeProcess && !bridgeProcess.killed) bridgeProcess.kill();
        }, 2000);
    }
}

// ── File operations ────────────────────────────────────────

async function applyCodeBlock(filePath, codeContent) {
    const projectRoot = getWorkspaceRoot();
    const fullPath = path.isAbsolute(filePath) ? filePath : path.join(projectRoot, filePath);
    const uri = vscode.Uri.file(fullPath);
    try {
        let existingContent = '';
        try { const d = await vscode.workspace.openTextDocument(uri); existingContent = d.getText(); } catch (e) {}
        const edit = new vscode.WorkspaceEdit();
        if (existingContent) {
            edit.replace(uri, new vscode.Range(0, 0, existingContent.split('\n').length, 0), codeContent);
        } else {
            edit.createFile(uri, { overwrite: false });
            edit.insert(uri, new vscode.Position(0, 0), codeContent);
        }
        await vscode.workspace.applyEdit(edit);
        const doc = await vscode.workspace.openTextDocument(uri);
        await doc.save();
        const o = await vscode.workspace.openTextDocument({ content: existingContent || '', language: doc.languageId });
        const m = await vscode.workspace.openTextDocument({ content: codeContent, language: doc.languageId });
        await vscode.commands.executeCommand('vscode.diff', o.uri, m.uri, `${path.basename(filePath)}: Changes`);
        await vscode.window.showTextDocument(doc, { preview: false });
        return true;
    } catch (err) {
        vscode.window.showErrorMessage(`Apply failed: ${err.message}`);
        return false;
    }
}

// ── Diagnostics ────────────────────────────────────────────

function parseDiagnostics(text) {
    const diags = [], seen = new Set();
    const re = /ISSUE\|(.+?)\|(\d+)\|(\w+)\|(.+)/g;
    let m;
    while ((m = re.exec(text)) !== null) {
        const key = `${m[1]}:${m[2]}`;
        if (seen.has(key)) continue;
        seen.add(key);
        diags.push({ filePath: m[1].trim(), line: parseInt(m[2], 10) - 1,
            severity: m[3].trim().toLowerCase() === 'error' ? 0 : m[3].trim().toLowerCase() === 'warning' ? 1 : 2,
            message: m[4].trim() });
    }
    return diags;
}

function postDiagnostics(collection, diags) {
    collection.clear();
    const byFile = new Map();
    const root = getWorkspaceRoot();
    for (const d of diags) {
        const r = path.isAbsolute(d.filePath) ? d.filePath : path.join(root, d.filePath);
        if (!byFile.has(r)) byFile.set(r, []);
        byFile.get(r).push(d);
    }
    for (const [fp, fds] of byFile) {
        collection.set(vscode.Uri.file(fp), fds.map(d =>
            new vscode.Diagnostic(new vscode.Range(d.line, 0, d.line, 999), d.message,
                d.severity === 0 ? vscode.DiagnosticSeverity.Error : d.severity === 1 ? vscode.DiagnosticSeverity.Warning : vscode.DiagnosticSeverity.Information)));
    }
}

// ── Quick actions ──────────────────────────────────────────

const QUICK_ACTIONS = {
    'smart-commit':  { label: '🧠 提交', prompt: 'Read git diff. Write a short Chinese conventional commit message. Run git_add_commit with it, then git_push.' },
    'clean-code':    { label: '🧹 清理', prompt: 'You are a code cleaner. Do NOT use any methodology/TDD/planning workflow. Just do these steps directly: 1) search_files for "print(" and "import" patterns in Python files, 2) read_file to check each match, 3) edit_file to remove debug prints and unused imports, 4) run_format, 5) run_lint --fix. Skip methodology checks completely.' },
    'add-tests':     { label: '🧪 补测试', prompt: 'Find the 3 most important Python functions without test coverage. Write pytest tests. Run with run_test to verify.' },
    'add-comments':  { label: '📝 注释', prompt: 'Scan core/ and ui/ Python files. Add Chinese docstrings to public functions and classes missing documentation. Use edit_file.' },
    'changelog':     { label: '📋 日志', prompt: 'Read recent git commits with git_log. Generate CHANGELOG.md organized by feature/bugfix/chore in Chinese.' },
    'dep-check':     { label: '🔐 依赖', prompt: 'Check Python dependencies: run pip list --outdated via run_bash. Write findings to DEPENDENCY_REPORT.md.' },
    'readme':        { label: '📖 说明', prompt: 'Analyze this project structure and key files. Generate a comprehensive Chinese README.md.' }
};

async function handleQuickAction(action) {
    const def = QUICK_ACTIONS[action];
    if (!def) return;
    await vscode.commands.executeCommand('crux.openPanel');

    const actionId = 'qa_' + action + '_' + Date.now();
    if (currentPanel) {
        currentPanel.webview.postMessage({ command: 'addMessage', role: 'user', content: def.label + ' (one-click)' });
    }

    try {
        await ensureBridge();
        const handler = {
            resolve: () => {
                if (currentPanel) {
                    currentPanel.webview.postMessage({ command: 'streamEnd', id: actionId });
                    currentPanel.webview.postMessage({ command: 'addMessage', role: 'info', content: def.label + ' done' });
                }
            },
            reject: (err) => {
                if (currentPanel) {
                    currentPanel.webview.postMessage({ command: 'addMessage', role: 'info', content: def.label + ' error: ' + err.message });
                }
            },
            onMessage: (msg) => {
                if (currentPanel) {
                    currentPanel.webview.postMessage({
                        command: 'streamChunk', id: actionId,
                        type: msg.type, content: msg.content || '',
                        tool: msg.tool || '', message: msg.message || '', success: msg.success
                    });
                }
            }
        };
        pendingRequests.set(actionId, handler);
        isBridgeBusy = true;
        writeToBridge(JSON.stringify({ id: actionId, method: 'chat', params: { prompt: def.prompt, files: [] } }) + '\n');
    } catch (err) {
        vscode.window.showErrorMessage(`${def.label} error: ${err.message}`);
    }
}

// ── Webview HTML ───────────────────────────────────────────

function getWebviewContent(extensionUri) {
    return require('fs').readFileSync(
        vscode.Uri.joinPath(extensionUri, 'media', 'webview.html').fsPath, 'utf8');
}

// ── Extension lifecycle ────────────────────────────────────

function activate(context) {
    log('CRUX Agent v0.3.0 activating...');
    startBridge().then(() => log('Bridge ready')).catch(err => log(`Bridge start: ${err.message}`));

    const cruxDiagnostics = vscode.languages.createDiagnosticCollection('CRUX Audit');
    context.subscriptions.push(cruxDiagnostics);

    const openPanelCmd = vscode.commands.registerCommand('crux.openPanel', () => {
        if (currentPanel) { currentPanel.reveal(vscode.ViewColumn.Beside); return; }
        currentPanel = vscode.window.createWebviewPanel('cruxAgent', 'CRUX Agent', vscode.ViewColumn.Beside, {
            enableScripts: true, retainContextWhenHidden: true,
            localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, 'media')]
        });
        currentPanel.webview.html = getWebviewContent(context.extensionUri);

        currentPanel.webview.onDidReceiveMessage(async (message) => {
            switch (message.command) {
                case 'send': {
                    if (!message.text || !message.text.trim()) break;
                    const files = getActiveEditorContext();
                    const assistId = 'msg_' + Date.now();
                    if (currentPanel) {
                        currentPanel.webview.postMessage({ command: 'addMessage', role: 'user', content: message.text });
                    }
                    try {
                        await ensureBridge();
                        const handler = {
                            resolve: () => { if (currentPanel) currentPanel.webview.postMessage({ command: 'streamEnd', id: assistId }); },
                            reject: (err) => {
                                if (currentPanel) {
                                    currentPanel.webview.postMessage({ command: 'streamChunk', id: assistId, type: 'error', content: err.message });
                                    currentPanel.webview.postMessage({ command: 'streamEnd', id: assistId });
                                }
                            },
                            onMessage: (msg) => {
                                if (currentPanel) {
                                    currentPanel.webview.postMessage({
                                        command: 'streamChunk', id: assistId,
                                        type: msg.type, content: msg.content || '',
                                        tool: msg.tool || '', message: msg.message || '', success: msg.success
                                    });
                                }
                            }
                        };
                        pendingRequests.set(assistId, handler);
                        isBridgeBusy = true;
                        writeToBridge(JSON.stringify({ id: assistId, method: 'chat', params: { prompt: message.text, files } }) + '\n');
                    } catch (err) {
                        if (currentPanel) {
                            currentPanel.webview.postMessage({ command: 'streamChunk', id: assistId, type: 'error', content: err.message });
                            currentPanel.webview.postMessage({ command: 'streamEnd', id: assistId });
                        }
                    }
                    break;
                }
                case 'applyEdit': {
                    const ok = await applyCodeBlock(message.filePath, message.content);
                    if (currentPanel) currentPanel.webview.postMessage({ command: 'editResult', id: message.editId, success: ok });
                    break;
                }
                case 'audit': vscode.commands.executeCommand('crux.audit'); break;
                case 'quickAction': handleQuickAction(message.action); break;
                case 'clear':
                    try {
                        await ensureBridge();
                        writeToBridge(JSON.stringify({ id: 'reset_' + Date.now(), method: 'reset', params: {} }) + '\n');
                    } catch (e) {}
                    if (currentPanel) currentPanel.webview.postMessage({ command: 'clear' });
                    break;
            }
        });
        currentPanel.onDidDispose(() => { currentPanel = null; }, null, context.subscriptions);
    });

    const sendSelectionCmd = vscode.commands.registerCommand('crux.sendToAgent', async () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;
        const s = editor.document.getText(editor.selection);
        if (!s.trim()) return;
        await vscode.commands.executeCommand('crux.openPanel');
        setTimeout(() => {
            if (currentPanel) currentPanel.webview.postMessage({
                command: 'sendFromEditor',
                text: `Look at ${vscode.workspace.asRelativePath(editor.document.uri)}:\n\`\`\`\n${s}\n\`\`\``
            });
        }, 300);
    });

    const resetCmd = vscode.commands.registerCommand('crux.resetChat', async () => {
        try {
            await ensureBridge();
            writeToBridge(JSON.stringify({ id: 'reset_' + Date.now(), method: 'reset', params: {} }) + '\n');
        } catch (e) {}
        if (currentPanel) currentPanel.webview.postMessage({ command: 'clear' });
    });

    const auditCmd = vscode.commands.registerCommand('crux.audit', async () => {
        await vscode.commands.executeCommand('crux.openPanel');
        const auditId = 'audit_' + Date.now();
        const msgs = [];
        if (currentPanel) currentPanel.webview.postMessage({ command: 'addMessage', role: 'user', content: '🔍 Audit' });
        try {
            await ensureBridge();
            const handler = {
                resolve: () => {
                    const diags = parseDiagnostics(msgs.join(''));
                    postDiagnostics(cruxDiagnostics, diags);
                    if (currentPanel) {
                        currentPanel.webview.postMessage({ command: 'streamEnd', id: auditId });
                        currentPanel.webview.postMessage({ command: 'addMessage', role: 'info', content: `Found ${diags.length} issues → Problems panel` });
                    }
                    vscode.window.showInformationMessage(`CRUX Audit: ${diags.length} issues`);
                },
                reject: (err) => { vscode.window.showErrorMessage('Audit failed: ' + err.message); },
                onMessage: (msg) => {
                    if (msg.type === 'text') msgs.push(msg.content || '');
                    if (currentPanel) {
                        currentPanel.webview.postMessage({
                            command: 'streamChunk', id: auditId,
                            type: msg.type, content: msg.content || '',
                            tool: msg.tool || '', message: msg.message || '', success: msg.success
                        });
                    }
                }
            };
            pendingRequests.set(auditId, handler);
            isBridgeBusy = true;
            writeToBridge(JSON.stringify({ id: auditId, method: 'chat', params: {
                prompt: `Run code audit: run_lint, code_review on recent files, search for hardcoded credentials/bare except/print(). For each issue: ISSUE|path|LINE|severity|description`,
                files: []
            } }) + '\n');
        } catch (err) { vscode.window.showErrorMessage('Audit: ' + err.message); }
    });

    const quickCmdNames = ['smartCommit', 'cleanCode', 'addTests', 'addComments', 'changelog', 'depCheck', 'readme'];
    const quickCmds = quickCmdNames.map(n => {
        const a = n.replace(/([A-Z])/g, '-$1').toLowerCase().replace(/^-/, '');
        return vscode.commands.registerCommand(`crux.${n}`, () => handleQuickAction(a));
    });

    context.subscriptions.push(openPanelCmd, sendSelectionCmd, resetCmd, auditCmd, ...quickCmds);

    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.text = '$(hubot) CRUX';
    statusBarItem.tooltip = 'Open CRUX Agent Panel';
    statusBarItem.command = 'crux.openPanel';
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);
}

async function deactivate() {
    log('CRUX Agent deactivating...');
    quitBridge();
    pendingRequests.clear();
}

module.exports = { activate, deactivate };
