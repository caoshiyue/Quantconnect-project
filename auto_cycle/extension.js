const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');

function getOut() {
    if (!global._nbOut) global._nbOut = vscode.window.createOutputChannel('autoNotebook');
    return global._nbOut;
}

// ---------- 运行 Notebook ----------
async function runNotebook() {
    const out = getOut();
    out.appendLine('--- Running Notebook ---');

    await vscode.commands.executeCommand('workbench.action.focusFirstEditorGroup');
    await vscode.commands.executeCommand('notebook.focusTop');
    await new Promise(r => setTimeout(r, 500));

    await vscode.commands.executeCommand('notebook.execute');
    out.appendLine('✅ Notebook executed');
}



async function runPythonScript(pyPath) {
    const workspace = vscode.workspace.workspaceFolders[0].uri.fsPath;
    return new Promise((resolve, reject) => {
        exec(`python "${pyPath}"`, { cwd: workspace }, (err, stdout, stderr) => {
            const out = getOut();
            const stdoutStr = stdout.toString('gbk');
            const stderrStr = stderr.toString('gbk');
            out.appendLine(`--- Running Python script: ${pyPath} ---`);
            out.appendLine(stdoutStr);
            out.appendLine(stderrStr);
            if (err) reject(err);
            else resolve(stdout);
        });
    });
}



// ---------- 修改 Notebook 中的日期 ----------
function incrementNotebookDate(nbPath) {
    const out = getOut();
    const nbData = JSON.parse(fs.readFileSync(nbPath, 'utf8'));

    let modified = false;

    // 遍历 cell 查找包含 year = 202001 的行
    for (let cell of nbData.cells) {
        for (let i = 0; i < cell.source.length; i++) {
            let line = cell.source[i];
            const match = line.match(/year\s*=\s*(\d{6})/);
            if (match) {
                let val = match[1]; // 例如 202001
                let year = parseInt(val.slice(0, 4), 10);
                let month = parseInt(val.slice(4, 6), 10);

                // 月份 +1
                month += 1;
                if (month > 12) {
                    month = 1;
                    year += 1;
                }

                // 如果超过 202412 就不再修改
                if (year > 2024 || (year === 2024 && month > 12)) {
                    out.appendLine('Reached 2024-12, stopping increment.');
                    return false; // 停止循环
                }

                // 格式化为 YYYYMM
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

            // 2️⃣ 运行 Python 脚本
            await new Promise(r => setTimeout(r, 5000));

            await runPythonScript(pyPath);

            // 3️⃣ 修改 Notebook 日期
            keepRunning = incrementNotebookDate(nbPath);
            if (!keepRunning) break;

            // 4️⃣ 再次运行 Notebook
            await runNotebook();
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