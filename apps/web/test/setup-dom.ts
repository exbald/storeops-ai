import { Window } from "happy-dom";

const win = new Window();
(globalThis as any).window = win;
(globalThis as any).document = win.document;
(globalThis as any).HTMLElement = win.HTMLElement;
(globalThis as any).customElements = win.customElements;
Object.defineProperty(globalThis, "navigator", {
  value: win.navigator,
  configurable: true,
  writable: true,
});
(globalThis as any).Event = win.Event;
(globalThis as any).CustomEvent = win.CustomEvent;
(globalThis as any).Node = win.Node;
(globalThis as any).self = win;
(globalThis as any).requestIdleCallback = (cb: any) => setTimeout(cb, 1);
(globalThis as any).cancelIdleCallback = (id: any) => clearTimeout(id);
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
