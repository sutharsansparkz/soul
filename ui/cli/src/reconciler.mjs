import ReactReconciler from "react-reconciler";

const ANSI = {
  reset: "\x1b[0m",
  dim: "\x1b[2m",
  bold: "\x1b[1m",
  colors: {
    red: "\x1b[31m",
    green: "\x1b[32m",
    yellow: "\x1b[33m",
    blue: "\x1b[34m",
    magenta: "\x1b[35m",
    cyan: "\x1b[36m",
    white: "\x1b[37m",
  },
};

function createNode(type, props = {}) {
  return {type, props, children: []};
}

function styleLine(text, props = {}) {
  const codes = [];
  if (props.bold) {
    codes.push(ANSI.bold);
  }
  if (props.dim || props.dimColor) {
    codes.push(ANSI.dim);
  }
  if (props.color && ANSI.colors[props.color]) {
    codes.push(ANSI.colors[props.color]);
  }
  if (codes.length === 0) {
    return text;
  }
  return `${codes.join("")}${text}${ANSI.reset}`;
}

function textContent(node) {
  if (!node) {
    return "";
  }
  if (node.type === "TEXT") {
    return node.text;
  }
  return (node.children || []).map(textContent).join("");
}

function renderNodeToLines(node) {
  if (!node) {
    return [];
  }
  if (node.type === "TEXT") {
    return [node.text];
  }
  if (node.type === "line") {
    const inline = node.props.text ? String(node.props.text) : textContent(node);
    return [styleLine(inline, node.props)];
  }
  if (node.type === "spacer") {
    const size = Number(node.props.size ?? 1);
    return Array.from({length: Math.max(1, size)}, () => "");
  }
  const lines = [];
  for (const child of node.children || []) {
    lines.push(...renderNodeToLines(child));
  }
  return lines;
}

function renderContainer(container) {
  const lines = [];
  for (const child of container.children) {
    lines.push(...renderNodeToLines(child));
  }
  const payload = lines.join("\n");
  process.stdout.write("\x1b[2J\x1b[H");
  process.stdout.write(payload);
  process.stdout.write("\n");
}

const hostConfig = {
  now: Date.now,
  getRootHostContext() {
    return null;
  },
  getChildHostContext() {
    return null;
  },
  prepareForCommit() {
    return null;
  },
  resetAfterCommit(container) {
    renderContainer(container);
  },
  shouldSetTextContent() {
    return false;
  },
  createInstance(type, props) {
    return createNode(type, props);
  },
  createTextInstance(text) {
    return {type: "TEXT", text: String(text)};
  },
  appendInitialChild(parent, child) {
    parent.children.push(child);
  },
  finalizeInitialChildren() {
    return false;
  },
  appendChild(parent, child) {
    parent.children.push(child);
  },
  appendChildToContainer(container, child) {
    container.children.push(child);
  },
  removeChild(parent, child) {
    const index = parent.children.indexOf(child);
    if (index >= 0) {
      parent.children.splice(index, 1);
    }
  },
  removeChildFromContainer(container, child) {
    const index = container.children.indexOf(child);
    if (index >= 0) {
      container.children.splice(index, 1);
    }
  },
  insertBefore(parent, child, beforeChild) {
    const beforeIndex = parent.children.indexOf(beforeChild);
    if (beforeIndex < 0) {
      parent.children.push(child);
      return;
    }
    parent.children.splice(beforeIndex, 0, child);
  },
  insertInContainerBefore(container, child, beforeChild) {
    const beforeIndex = container.children.indexOf(beforeChild);
    if (beforeIndex < 0) {
      container.children.push(child);
      return;
    }
    container.children.splice(beforeIndex, 0, child);
  },
  prepareUpdate() {
    return true;
  },
  commitUpdate(instance, _updatePayload, _type, oldProps, newProps) {
    instance.props = {...newProps, children: newProps.children ?? oldProps.children};
  },
  commitTextUpdate(textInstance, oldText, newText) {
    if (oldText !== newText) {
      textInstance.text = String(newText);
    }
  },
  clearContainer(container) {
    container.children = [];
  },
  getPublicInstance(instance) {
    return instance;
  },
  scheduleTimeout: setTimeout,
  cancelTimeout: clearTimeout,
  noTimeout: -1,
  isPrimaryRenderer: true,
  supportsMutation: true,
  supportsPersistence: false,
  supportsHydration: false,
};

const reconciler = ReactReconciler(hostConfig);

export function render(element) {
  const container = {children: []};
  const root = reconciler.createContainer(container, 0, null, false, null, "", console.error, null);
  reconciler.updateContainer(element, root, null, null);
  return {
    rerender(nextElement) {
      reconciler.updateContainer(nextElement, root, null, null);
    },
    unmount() {
      reconciler.updateContainer(null, root, null, null);
    },
  };
}
