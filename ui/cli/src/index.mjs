import React, {useCallback, useEffect, useMemo, useState} from "react";
import {Box, Text, render, useApp, useInput} from "ink";
import TextInput from "ink-text-input";
import {spawn} from "node:child_process";

function parseArgs(argv) {
  const args = {python: "python"};
  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (token === "--python" && argv[index + 1]) {
      args.python = argv[index + 1];
      index += 1;
    }
  }
  return args;
}

function runBridge(python, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(python, ["-m", "soul.cli_support.ink_bridge", ...args], {
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", chunk => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", chunk => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", code => {
      if (code !== 0) {
        reject(new Error(stderr.trim() || stdout.trim() || `bridge exited with code ${code}`));
        return;
      }
      const line = stdout
        .split("\n")
        .map(item => item.trim())
        .find(Boolean);
      if (!line) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(line));
      } catch (error) {
        reject(new Error(`invalid bridge response: ${line}`));
      }
    });
  });
}

function App({python}) {
  const {exit} = useApp();
  const [sessionId, setSessionId] = useState(null);
  const [soulName, setSoulName] = useState("SOUL");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(true);
  const [status, setStatus] = useState("Starting session...");
  const [lastMood, setLastMood] = useState(null);
  const [error, setError] = useState(null);

  const visibleMessages = useMemo(() => messages.slice(-12), [messages]);

  const closeSession = useCallback(async () => {
    if (!sessionId) {
      return;
    }
    try {
      await runBridge(python, ["close", "--session-id", sessionId]);
    } catch {
      // Swallow close errors to avoid trapping the user in the UI.
    }
  }, [python, sessionId]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const started = await runBridge(python, ["start"]);
        if (cancelled) {
          return;
        }
        setSessionId(started.session_id ?? null);
        setSoulName(started.soul_name ?? "SOUL");
        setBusy(false);
        setStatus("Connected");
      } catch (err) {
        if (cancelled) {
          return;
        }
        setBusy(false);
        setError(err.message);
      }
    })();

    return () => {
      cancelled = true;
      void closeSession();
    };
  }, [closeSession, python]);

  useInput((value, key) => {
    if (key.ctrl && value === "c") {
      void closeSession();
      exit();
    }
  });

  const submit = useCallback(
    async text => {
      const trimmed = text.trim();
      if (!trimmed || busy || !sessionId) {
        return;
      }
      setInput("");

      if (trimmed === "/quit") {
        await closeSession();
        exit();
        return;
      }
      if (trimmed === "/mood") {
        if (lastMood) {
          setMessages(current => [
            ...current,
            {
              role: "system",
              text: `Mood now: ${lastMood.companion_state} (you: ${lastMood.user_mood})`,
            },
          ]);
        } else {
          setMessages(current => [...current, {role: "system", text: "No mood yet in this session."}]);
        }
        return;
      }

      setMessages(current => [...current, {role: "user", text: trimmed}]);
      setBusy(true);
      setStatus(`${soulName} is thinking...`);
      try {
        const response = await runBridge(python, ["turn", "--session-id", sessionId, "--user-input", trimmed]);
        const replyText = response.assistant_text ?? "";
        setLastMood(response.mood ?? null);
        setMessages(current => [
          ...current,
          {
            role: "assistant",
            text: replyText,
          },
        ]);
        setStatus(response.mood ? `${response.mood.companion_state} (you: ${response.mood.user_mood})` : "Connected");
      } catch (err) {
        setMessages(current => [...current, {role: "system", text: `Turn failed: ${err.message}`}]);
        setStatus("Error");
      } finally {
        setBusy(false);
      }
    },
    [busy, closeSession, exit, lastMood, python, sessionId, soulName]
  );

  return (
    React.createElement(
      Box,
      {flexDirection: "column"},
      React.createElement(Text, {color: "magenta"}, `${soulName} Ink Chat`),
      React.createElement(Text, {dimColor: true}, "Commands: /mood, /quit, Ctrl+C"),
      error ? React.createElement(Text, {color: "red"}, `Startup failed: ${error}`) : null,
      React.createElement(Text, {dimColor: true}, `Status: ${status}`),
      React.createElement(Box, {marginTop: 1, flexDirection: "column"}, visibleMessages.map((entry, index) => {
        const color = entry.role === "assistant" ? "magenta" : entry.role === "user" ? "cyan" : "yellow";
        const prefix = entry.role === "assistant" ? soulName : entry.role === "user" ? "You" : "System";
        return React.createElement(Text, {key: `${entry.role}-${index}`, color}, `${prefix}: ${entry.text}`);
      })),
      React.createElement(Box, {marginTop: 1},
        React.createElement(Text, {color: "cyan"}, "You: "),
        React.createElement(TextInput, {
          value: input,
          onChange: setInput,
          onSubmit: submit,
          placeholder: sessionId ? "Type a message..." : "Waiting for session...",
          focus: Boolean(sessionId && !busy && !error),
        })
      )
    )
  );
}

const args = parseArgs(process.argv.slice(2));
render(React.createElement(App, {python: args.python}));
