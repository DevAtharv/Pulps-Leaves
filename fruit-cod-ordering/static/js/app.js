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
  if (text) text.textContent = isLoading ? "Submitting..." : "Place Order";
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

function initHomeSlider() {
  const slider = document.getElementById("homeSlider");
  if (!slider) return;

  const slides = Array.from(slider.querySelectorAll(".hero-slide"));
  const dots = Array.from(slider.querySelectorAll("[data-slider-dot]"));
  const previous = slider.querySelector("[data-slider-prev]");
  const next = slider.querySelector("[data-slider-next]");
  if (slides.length < 2) return;

  let activeIndex = 0;
  let timerId = null;

  function showSlide(index) {
    activeIndex = (index + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => {
      slide.classList.toggle("active", slideIndex === activeIndex);
    });
    dots.forEach((dot, dotIndex) => {
      dot.classList.toggle("active", dotIndex === activeIndex);
    });
  }

  function restartTimer() {
    window.clearInterval(timerId);
    timerId = window.setInterval(() => showSlide(activeIndex + 1), 4200);
  }

  previous?.addEventListener("click", () => {
    showSlide(activeIndex - 1);
    restartTimer();
  });

  next?.addEventListener("click", () => {
    showSlide(activeIndex + 1);
    restartTimer();
  });

  dots.forEach((dot) => {
    dot.addEventListener("click", () => {
      showSlide(Number(dot.dataset.sliderDot || 0));
      restartTimer();
    });
  });

  showSlide(0);
  restartTimer();
}

initHomeSlider();

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
