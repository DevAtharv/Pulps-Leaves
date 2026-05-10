const toastElement = document.getElementById("appToast");
const toast = toastElement && window.bootstrap ? new bootstrap.Toast(toastElement) : null;

function showToast(message) {
  if (!toastElement || !toast) return;
  toastElement.querySelector(".toast-body").textContent = message;
  toast.show();
}

function formToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function setLoading(form, isLoading) {
  const button = form.querySelector("button[type='submit']");
  if (!button) return;
  const spinner = button.querySelector(".spinner-border");
  const text = button.querySelector(".button-text");
  button.disabled = isLoading;
  if (spinner) spinner.classList.toggle("d-none", !isLoading);
  if (text) text.textContent = isLoading ? "Submitting..." : "Submit COD Order";
}

function showResult(targetId, message, isError = false) {
  const target = document.getElementById(targetId);
  target.classList.remove("d-none", "error");
  target.classList.toggle("error", isError);
  target.textContent = message;
}

async function readJsonResponse(response) {
  const text = await response.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch (error) {
    return {
      ok: false,
      error: text.slice(0, 180) || "Server returned an unexpected response.",
    };
  }
}

function errorMessageFromPayload(data, fallback) {
  if (data.errors) return Object.values(data.errors).join(" ");
  return data.error || fallback;
}

document.querySelectorAll(".select-product").forEach((button) => {
  button.addEventListener("click", () => {
    document.getElementById("product").value = button.dataset.product;
    document.getElementById("order").scrollIntoView({ behavior: "smooth" });
  });
});

const orderForm = document.getElementById("orderForm");
if (orderForm) {
  orderForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    setLoading(orderForm, true);
    try {
      const response = await fetch("/api/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formToObject(orderForm)),
      });
      const data = await readJsonResponse(response);
      if (!response.ok || !data.ok) {
        showResult("orderResult", errorMessageFromPayload(data, "Order could not be submitted."), true);
        showToast("Please check the order fields.");
        return;
      }
      const order = data.order;
      const message = `Order placed. Order ID: ${order["Order ID"]}. Status: ${order["Order Status"]}.`;
      showResult("orderResult", message);
      showToast("Order saved.");
      orderForm.reset();
    } catch (error) {
      showResult("orderResult", `Connection failed: ${error.message}`, true);
    } finally {
      setLoading(orderForm, false);
    }
  });
}

const editForm = document.getElementById("editForm");
if (editForm) {
  editForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const payload = formToObject(editForm);
    const orderId = payload.order_id;
    delete payload.order_id;
    try {
      const response = await fetch(`/api/orders/${encodeURIComponent(orderId)}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await readJsonResponse(response);
      if (!response.ok || !data.ok) {
        showResult("editResult", errorMessageFromPayload(data, "Order could not be updated."), true);
        return;
      }
      showResult("editResult", `Updated ${data.order_id}.`);
      showToast("Order updated.");
    } catch (error) {
      showResult("editResult", `Connection failed: ${error.message}`, true);
    }
  });
}

const chatMessages = document.getElementById("chatMessages");
const chatForm = document.getElementById("chatForm");
const chatInput = document.getElementById("chatInput");
const chatUserId =
  localStorage.getItem("pl_chat_user_id") ||
  `web-${window.crypto?.randomUUID ? crypto.randomUUID() : Date.now()}`;
localStorage.setItem("pl_chat_user_id", chatUserId);

function addBubble(message, who) {
  if (!chatMessages) return;
  const bubble = document.createElement("div");
  bubble.className = `bubble ${who}`;
  bubble.textContent = message;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function sendChat(message, renderUser = true) {
  if (renderUser) addBubble(message, "user");
  const typing = document.createElement("div");
  typing.className = "bubble bot";
  typing.textContent = "Typing...";
  chatMessages.appendChild(typing);
  chatMessages.scrollTop = chatMessages.scrollHeight;

  try {
    const response = await fetch("/api/chatbot/message", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: chatUserId, message }),
    });
    const data = await readJsonResponse(response);
    typing.remove();
    addBubble(data.reply, "bot");
  } catch (error) {
    typing.remove();
    addBubble("The assistant is unavailable right now. Please try again.", "bot");
  }
}

if (chatForm) {
  chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const message = chatInput.value.trim();
    if (!message) return;
    chatInput.value = "";
    sendChat(message);
  });
  sendChat("menu", false);
}
