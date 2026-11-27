// A minimal fence element for lectern's tests: a named Run button and a live output.
import { runLabel } from "./demo-glue.js";

class DemoCell extends HTMLElement {
  connectedCallback() {
    const code = this.textContent;
    this.textContent = "";
    const pre = document.createElement("pre");
    pre.textContent = code;
    const button = document.createElement("button");
    button.textContent = runLabel;
    const output = document.createElement("div");
    output.setAttribute("aria-live", "polite");
    button.addEventListener("click", () => { output.textContent = code; });
    this.addEventListener("keydown", (e) => e.stopPropagation());
    this.dataset.code = code;
    this.append(pre, button, output);
  }
}
customElements.define("demo-cell", DemoCell);
