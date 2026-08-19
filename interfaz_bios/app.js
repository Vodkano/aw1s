const chatForm = document.querySelector("#chat-form");
const messageInput = document.querySelector("#message-input");
const chatWindow = document.querySelector("#chat-window");
const sendButton = document.querySelector(".send-button");
const clock = document.querySelector("#clock");

function addMessage(role, text, code = "", language = "") {
  const message = document.createElement("div");
  message.className = `message ${role}-message`;
  const label = role === "user" ? "USER" : "OLLAMA";
  message.innerHTML = `<span class="message-label">${label}</span><p></p>`;
  message.querySelector("p").textContent = text;
  if (code) {
    const codePanel = document.createElement("div");
    codePanel.className = "code-panel";
    const header = document.createElement("div");
    header.className = "code-header";
    const languageLabel = document.createElement("span");
    languageLabel.textContent = language.toUpperCase();
    const executeButton = document.createElement("button");
    executeButton.className = "execute-button";
    executeButton.type = "button";
    executeButton.textContent = "OPEN TERMINAL >";
    header.append(languageLabel, executeButton);
    const codeElement = document.createElement("pre");
    codePanel.append(header, codeElement);
    codeElement.textContent = code;
    executeButton.addEventListener("click", () => executeCode(code, language));
    message.appendChild(codePanel);
  }
  chatWindow.appendChild(message);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

async function executeCode(code, language) {
  try {
    const response = await fetch("/api/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, language }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "No se pudo abrir Terminal");
  } catch (error) {
    addMessage("assistant", `ERROR // ${error.message}`);
  }
}

function setClock() {
  clock.textContent = new Date().toLocaleTimeString("es-CL", { hour12: false });
}

async function submitMessage(event) {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message || sendButton.disabled) return;

  addMessage("user", message);
  messageInput.value = "";
  sendButton.disabled = true;
  sendButton.textContent = "PROCESSING...";

  try {
    const response = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Fallo de comunicacion");
    addMessage("assistant", payload.answer, payload.code, payload.language);
  } catch (error) {
    addMessage("assistant", `ERROR // ${error.message}`);
  } finally {
    sendButton.disabled = false;
    sendButton.innerHTML = "TRANSMIT <span>&gt;</span>";
    messageInput.focus();
  }
}

document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".nav-button").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view").forEach((view) => { view.hidden = true; });
    button.classList.add("active");
    document.querySelector(`[data-panel="${button.dataset.view}"]`).hidden = false;
  });
});

chatForm.addEventListener("submit", submitMessage);
messageInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    chatForm.requestSubmit();
  }
});

setClock();
setInterval(setClock, 1000);
messageInput.focus();
