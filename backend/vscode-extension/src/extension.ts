import * as vscode from "vscode";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import archiver from "archiver";

function getBackendBaseUrl(): string {
  const cfg = vscode.workspace.getConfiguration("aiDocGen");
  const raw = cfg.get<string>("backendUrl", "http://127.0.0.1:8000");
  return raw.replace(/\/+$/, ""); // remove trailing slash
}

function getUseAi(): boolean {
  const cfg = vscode.workspace.getConfiguration("aiDocGen");
  return cfg.get<boolean>("useAi", false);
}

function extToLanguage(ext: string): string {
  if (ext === ".py") return "python";
  if (ext === ".js") return "javascript";
  if (ext === ".java") return "java";
  if (ext === ".css") return "css";
  if (ext === ".html" || ext === ".htm") return "html";
  return "python";
}

export function activate(context: vscode.ExtensionContext) {
  console.log("✅ AI DocGen extension activated");

  // --------------------------------------------
  // Command: Generate docs for current file
  // --------------------------------------------
  const cmdCurrentFile = vscode.commands.registerCommand(
    "ai-docgen.generateForCurrentFile",
    async () => {
      try {
        const editor = vscode.window.activeTextEditor;
        if (!editor) {
          vscode.window.showErrorMessage("Open a file first.");
          return;
        }

        const baseUrl = getBackendBaseUrl();
        const useAi = getUseAi();

        const BACKEND_SINGLE_URL = `${baseUrl}/generate`;

        const code = editor.document.getText();
        const ext = path.extname(editor.document.fileName).toLowerCase();
        const lang = extToLanguage(ext);

        const payload = { language: lang, code, use_ai: useAi };

        const res = await fetch(BACKEND_SINGLE_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });

        if (!res.ok) {
          const errText = await res.text();
          vscode.window.showErrorMessage("Backend error: " + errText);
          return;
        }

        const data = (await res.json()) as any;

        const docText = String(data.documentation || "");
        const doc = await vscode.workspace.openTextDocument({
          content: docText,
          language: "markdown",
        });
        await vscode.window.showTextDocument(doc, { preview: false });

        vscode.window.showInformationMessage("✅ Documentation generated.");
      } catch (e: any) {
        vscode.window.showErrorMessage("Error: " + (e?.message || String(e)));
      }
    }
  );

  // --------------------------------------------
  // Command: Document entire folder (ZIP)
  // Saves to Downloads/docgen_project.zip
  // --------------------------------------------
  const cmdFolderZip = vscode.commands.registerCommand(
    "ai-docgen.documentFolderZip",
    async () => {
      try {
        const folders = vscode.workspace.workspaceFolders;
        if (!folders || folders.length === 0) {
          vscode.window.showErrorMessage(
            "Open a folder/project in VS Code first."
          );
          return;
        }

        const baseUrl = getBackendBaseUrl();
        const useAi = getUseAi();

        const BACKEND_ZIP_URL = `${baseUrl}/generate-zip-download`;

        const rootFolder = folders[0].uri.fsPath;
        const folderName = path.basename(rootFolder);

        vscode.window.showInformationMessage("📦 Zipping project folder...");

        const zipPath = path.join(os.tmpdir(), `${folderName}.zip`);

        await new Promise<void>((resolve, reject) => {
          const output = fs.createWriteStream(zipPath);
          const archive = archiver("zip", { zlib: { level: 9 } });

          output.on("close", () => resolve());

          archive.on("warning", (err: any) => {
            console.warn("archiver warning", err);
          });

          archive.on("error", (err: any) => {
            reject(err);
          });

          archive.pipe(output);
          archive.directory(rootFolder, false);
          archive.finalize();
        });

        vscode.window.showInformationMessage("📤 Sending folder to backend...");

        const form = new FormData();
        const zipBuffer = fs.readFileSync(zipPath);

        form.append("zip_file", new Blob([zipBuffer]), `${folderName}.zip`);
        form.append("preferred_language", "");
        form.append("use_ai", useAi ? "true" : "false");

        const res = await fetch(BACKEND_ZIP_URL, {
          method: "POST",
          body: form,
        });

        if (!res.ok) {
          const errText = await res.text();
          vscode.window.showErrorMessage("Backend failed: " + errText);
          return;
        }

        const downloads = path.join(os.homedir(), "Downloads");
        const savePath = path.join(downloads, "docgen_project.zip");

        const arrayBuf = await res.arrayBuffer();
        fs.writeFileSync(savePath, Buffer.from(arrayBuf));

        vscode.window.showInformationMessage("✅ ZIP saved to: " + savePath);

        vscode.commands.executeCommand(
          "revealFileInOS",
          vscode.Uri.file(savePath)
        );
      } catch (e: any) {
        vscode.window.showErrorMessage("Error: " + (e?.message || String(e)));
      }
    }
  );

  context.subscriptions.push(cmdCurrentFile);
  context.subscriptions.push(cmdFolderZip);
}

export function deactivate() {}