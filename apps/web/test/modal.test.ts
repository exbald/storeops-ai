/** Modal overlay must cover the whole viewport even inside spaced (space-y-*) layouts. */

import "./setup-dom";
import test from "node:test";
import assert from "node:assert/strict";
import React, { act } from "react";
import { createRoot } from "react-dom/client";

import { Modal } from "../src/components/ui/modal";

test("Modal: overlay cancels inherited sibling margins so it starts at the top of the viewport", async () => {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      React.createElement(
        "div",
        { className: "space-y-6" },
        React.createElement("p", null, "page"),
        React.createElement(Modal, { isOpen: true, onClose: () => {}, title: "T", children: "body" }),
      ),
    );
  });
  const overlay = container.querySelector('[role="dialog"]');
  assert.ok(overlay);
  assert.match(overlay.className, /(^|\s)!m-0(\s|$)/);
  await act(async () => root.unmount());
  container.remove();
});
