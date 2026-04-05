import React, {useEffect, useMemo, useState} from "react";
import {spawn} from "node:child_process";
import {dirname, resolve} from "node:path";
import {fileURLToPath} from "node:url";
import {render} from "./reconciler.mjs";

function parseArgs(argv) {
  const parsed = {python: "python", commandArgs: []};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--python" && argv[index + 1]) {
      parsed.python = argv[index + 1];
      index += 1;
      continue;
    }
    parsed.commandArgs.push(token);
  }
  return parsed;
}

function App({python, commandArgs}) {
  const [status, setStatus] = useState("starting");
  const [exitCode, setExitCode] = useState(null);
  const [lines, setLines] = useState([]);
  const [stderrLines, setStderrLines] = useState([]);
  const [spinnerTick, setSpinnerTick] = useState(0);

  const visibleLines = useMemo(() => lines.slice(-40), [lines]);
  const displayCommand = useMemo(() => commandArgs.join(" ").trim() || "(help)", [commandArgs]);
  const spinnerFrame = useMemo(() => {
    const frames = ["-", "\\", "|", "/"];
    return frames[spinnerTick % frames.length];
  }, [spinnerTick]);

  useEffect(() => {
    if (status !== "running") {
      return undefined;
    }
    const timer = setInterval(() => setSpinnerTick(current => current + 1), 90);
    return () => clearInterval(timer);
  }, [status]);

  useEffect(() => {
    const currentDir = dirname(fileURLToPath(import.meta.url));
    const uiDir = resolve(currentDir, "..");
    // `chat` and `ink-chat` use the dedicated React/Ink chat surface.
    const wantsChatUi = commandArgs[0] === "chat" || commandArgs[0] === "ink-chat";
    const chatArgs = commandArgs[0] === "ink-chat" ? commandArgs.slice(1) : commandArgs.slice(1);
    const child = wantsChatUi
      ? spawn(
          "npm",
          ["--prefix", uiDir, "run", "soul:ink-chat", "--", "--python", python, ...chatArgs],
          {stdio: "inherit"}
        )
      : spawn(
          python,
          ["-m", "soul.cli_support.react_bridge", "invoke", "--", ...commandArgs],
          {stdio: ["ignore", "pipe", "pipe"]}
        );

    let bridgeStdout = "";
    let bridgeStderr = "";
    if (!wantsChatUi) {
      child.stdout.on("data", chunk => {
        bridgeStdout += chunk.toString();
      });
      child.stderr.on("data", chunk => {
        bridgeStderr += chunk.toString();
      });
    }

    child.on("close", code => {
      if (!wantsChatUi) {
        const firstJsonLine = bridgeStdout
          .split("\n")
          .map(line => line.trim())
          .find(Boolean);
        if (firstJsonLine) {
          try {
            const payload = JSON.parse(firstJsonLine);
            const stdoutEntries = String(payload.stdout ?? "")
              .split("\n")
              .map(line => line.trimEnd())
              .filter(Boolean);
            const stderrEntries = String(payload.stderr ?? "")
              .split("\n")
              .map(line => line.trimEnd())
              .filter(Boolean);
            setLines(stdoutEntries);
            setStderrLines(stderrEntries);
            code = Number(payload.exit_code ?? code ?? 0);
          } catch {
            setLines(bridgeStdout.split("\n").filter(Boolean));
            setStderrLines(bridgeStderr.split("\n").filter(Boolean));
          }
        } else {
          setStderrLines(bridgeStderr.split("\n").filter(Boolean));
        }
      }
      setStatus("finished");
      setExitCode(code ?? 0);
      setTimeout(() => process.exit(code ?? 0), 80);
    });
    child.on("error", error => {
      setStatus("failed");
      setLines(current => [...current, `failed to start command: ${error.message}`]);
      setExitCode(1);
      setTimeout(() => process.exit(1), 80);
    });

    setStatus("running");
    return () => {
      child.kill("SIGTERM");
    };
  }, [commandArgs, python]);

  return React.createElement(
    "app",
    null,
    React.createElement("line", {color: "magenta", bold: true}, "SOUL React CLI"),
    React.createElement("line", {dim: true}, `Command: soul ${displayCommand}`),
    status === "running"
      ? React.createElement("line", {color: "green"}, `${spinnerFrame} Running...`)
      : React.createElement("line", {dim: true}, `Status: ${status}${exitCode === null ? "" : ` (${exitCode})`}`),
    React.createElement("spacer", {size: 1}),
    ...visibleLines.map((line, index) => React.createElement("line", {key: `line-${index}`}, line)),
    ...(stderrLines.length > 0 ? [React.createElement("spacer", {key: "stderr-gap", size: 1})] : []),
    ...stderrLines.map((line, index) => React.createElement("line", {key: `stderr-${index}`, color: "yellow"}, line))
  );
}

const parsed = parseArgs(process.argv.slice(2));
render(React.createElement(App, {python: parsed.python, commandArgs: parsed.commandArgs}));
