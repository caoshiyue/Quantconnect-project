const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

function getOut() {
    if (!global._nbOut) global._nbOut = vscode.window.createOutputChannel('autoNotebook');
    return global._nbOut;
}

// ---------- 等待工具 ----------
function delay(ms) {
    return new Promise(r => setTimeout(r, ms));
}

// ---------- 运行 Notebook ----------
async function runNotebook() {
    const out = getOut();
    out.appendLine('--- Running Notebook ---');

    await vscode.commands.executeCommand('workbench.action.focusFirstEditorGroup');
    await vscode.commands.executeCommand('notebook.focusTop');
    await delay(500);

    await vscode.commands.executeCommand('notebook.execute');
    out.appendLine('✅ Notebook executed');
}

// ---------- 运行 Python 脚本 ----------
async function runPythonScript(pyPath) {
    const workspace = vscode.workspace.workspaceFolders[0].uri.fsPath;
    return new Promise((resolve, reject) => {
        exec(`python "${pyPath}"`, { cwd: workspace, encoding: 'buffer' }, (err, stdout, stderr) => {
            const out = getOut();
            const stdoutStr = stdout.toString('utf8');
            const stderrStr = stderr.toString('utf8');
            out.appendLine(`--- Running Python script: ${pyPath} ---`);
            out.appendLine(stdoutStr);
            out.appendLine(stderrStr);
            if (err) reject(err);
            else resolve(stdoutStr);
        });
    });
}

// ---------- 清除输出 ----------
async function clearNotebookOutputs() {
    const out = getOut();
    out.appendLine('🧹 Clearing all cell outputs...');
    try {
        await vscode.commands.executeCommand('notebook.clearAllCellsOutputs');
        out.appendLine('✅ Cleared all outputs.');
    } catch (err) {
        out.appendLine('⚠️ Failed to clear outputs: ' + err.message);
    }
}

// ---------- 重启 Kernel ----------
async function restartKernel() {
    const out = getOut();
    out.appendLine('🔄 Restarting Jupyter kernel...');
    try {
        await vscode.commands.executeCommand('jupyter.restartkernel');
        out.appendLine('✅ Kernel restarted.');
        await delay(15000); // 等待 5 秒，确保 kernel 完全重启
    } catch (err) {
        out.appendLine('⚠️ Failed to restart kernel: ' + err.message);
    }
}

// ---------- 修改 Notebook 中的日期 ----------
function incrementNotebookDate(nbPath) {
    const out = getOut();
    const nbData = JSON.parse(fs.readFileSync(nbPath, 'utf8'));

    let modified = false;

    for (let cell of nbData.cells) {
        for (let i = 0; i < cell.source.length; i++) {
            let line = cell.source[i];
            const match = line.match(/year\s*=\s*(\d{6})/);
            if (match) {
                let val = match[1];
                let year = parseInt(val.slice(0, 4), 10);
                let month = parseInt(val.slice(4, 6), 10);

                month += 1;
                if (month > 12) {
                    month = 1;
                    year += 1;
                }

                if (year > 2024 || (year === 2024 && month > 12)) {
                    out.appendLine('Reached 2024-12, stopping increment.');
                    return false;
                }

                const newVal = `${year}${month.toString().padStart(2, '0')}`;
                cell.source[i] = line.replace(/\d{6}/, newVal);
                out.appendLine(`✅ Updated year: ${val} -> ${newVal}`);
                modified = true;
                break;
            }
        }
        if (modified) break;
    }

    fs.writeFileSync(nbPath, JSON.stringify(nbData, null, 2), 'utf8');
    return true;
}

// ---------- 主循环 ----------
async function runCycle() {
    const out = getOut();
    out.show(true);

    const workspace = vscode.workspace.workspaceFolders[0].uri.fsPath;
    const nbPath = path.join(workspace, '02_data_download_run.ipynb');
    const pyPath = path.join(workspace, '03_data_extract.py');

    try {
        let keepRunning = true;
        while (keepRunning) {
            out.appendLine('=== New cycle ===');

            // 1️⃣ 运行 Notebook
            await runNotebook();

            // 2️⃣ 等待 Notebook 执行完
            await delay(5000);

            // 3️⃣ 运行 Python 脚本
            await runPythonScript(pyPath);

            // 4️⃣ 清除输出
            await clearNotebookOutputs();

            // 5️⃣ 重启 Kernel 并等待
            await restartKernel();

            // 6️⃣ 修改 Notebook 日期
            keepRunning = incrementNotebookDate(nbPath);
            if (!keepRunning) break;

        }

        out.appendLine('✅ All cycles finished');
        vscode.window.showInformationMessage('All cycles finished');
    } catch (err) {
        out.appendLine('❌ Cycle failed: ' + err.message);
        vscode.window.showErrorMessage('Cycle failed: ' + err.message);
    }
}

// ---------- 插件激活 ----------
function activate(context) {
    const disposable = vscode.commands.registerCommand('autoNotebook.runCycle', runCycle);
    context.subscriptions.push(disposable, getOut());
}

function deactivate() {
    if (global._nbOut) global._nbOut.dispose();
}

module.exports = { activate, deactivate };