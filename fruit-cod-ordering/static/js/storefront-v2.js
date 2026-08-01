(() => {
  "use strict";

  const configNode = document.querySelector("#storefrontConfig");
  const config = configNode ? JSON.parse(configNode.textContent || "{}") : {};
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

  const siteHeader = document.querySelector("[data-site-header]");
  const nav = document.querySelector("[data-nav]");
  const menuToggle = document.querySelector("[data-menu-toggle]");
  const hero = document.querySelector("[data-hero]");
  const heroSlides = Array.from(document.querySelectorAll("[data-hero-slide]"));
  const heroDots = Array.from(document.querySelectorAll("[data-hero-dot]"));
  const drawer = document.querySelector("[data-drawer]");
  const drawerBackdrop = document.querySelector("[data-drawer-backdrop]");
  const orderForm = document.querySelector("[data-order-form]");
  const cartItemsNode = document.querySelector("[data-cart-items]");
  const cartInput = document.querySelector("[data-cart-input]");
  const cartCount = document.querySelector("[data-cart-count]");
  const summarySubtitle = document.querySelector("[data-summary-subtitle]");
  const summarySubtotal = document.querySelector("[data-summary-subtotal]");
  const summaryDelivery = document.querySelector("[data-summary-delivery]");
  const summarySavings = document.querySelector("[data-summary-savings]");
  const summaryTotal = document.querySelector("[data-summary-total]");
  const savingsLine = document.querySelector("[data-savings-line]");
  const submitButton = document.querySelector("[data-submit-order]");
  const orderResult = document.querySelector("[data-order-result]");
  const toast = document.querySelector("[data-toast]");
  const couponButtons = Array.from(document.querySelectorAll("[data-coupon-apply]"));
  const couponInput = document.querySelector("[data-coupon-input]");
  const couponFeedback = document.querySelector("[data-coupon-feedback]");
  const deliveryAddress = document.querySelector("[data-delivery-address]");
  const addressMapButton = document.querySelector("[data-address-map]");
  const accountModal = document.querySelector("[data-account-modal]");
  const orderSuccessModal = document.querySelector("[data-order-success-modal]");
  const orderSuccessId = document.querySelector("[data-order-success-id]");
  const orderSuccessCloseButton = document.querySelector("[data-order-success-close]");
  const accountTitle = document.querySelector("[data-account-title]");
  const accountCopy = document.querySelector("[data-account-copy]");
  const googleLoginButton = document.querySelector("[data-google-login]");
  const logoutButton = document.querySelector("[data-logout]");
  const orderHistoryButton = document.querySelector("[data-order-history]");
  const orderHistoryPanel = document.querySelector("[data-order-history-panel]");
  const orderHistoryStatus = document.querySelector("[data-order-history-status]");
  const orderHistoryList = document.querySelector("[data-order-history-list]");
  const paymentInputs = Array.from(document.querySelectorAll("input[name='payment_method']"));

  const DELIVERY_FREE_ABOVE = 699;
  const DELIVERY_CHARGE = 30;
  const ONLINE_PAYMENT_MINIMUM_SUBTOTAL = 699;
  const ONLINE_PAYMENT_DISCOUNT = 40;
  const CART_STORAGE_KEY = "pulps-leaves-cart-v4";

  let activeHeroSlide = 0;
  let heroTimer = null;
  let heroTouchStartX = null;
  let toastTimer = null;
  let checkoutToken = makeCheckoutToken();
  let razorpayCheckoutPromise = null;
  let appliedCouponCode = "";
  let checkoutBusy = false;
  let orderSuccessReturnFocus = null;

  const productCards = Array.from(document.querySelectorAll("[data-product]"));

  function productFromCard(card) {
    return {
      id: card.dataset.id,
      name: card.dataset.name,
      variant: card.dataset.variant,
      price: Number(card.dataset.price || 0),
      mrp: Number(card.dataset.mrp || 0),
      image: card.dataset.image,
      badge: card.dataset.cartBadge,
      secondaryTitle: card.dataset.secondaryTitle,
    };
  }

  function readProductVariants(card) {
    const node = card.querySelector("[data-product-variants]");
    if (!node) return [];
    try {
      const variants = JSON.parse(node.textContent || "[]");
      return Array.isArray(variants) ? variants : [];
    } catch (error) {
      return [];
    }
  }

  const productVariantsByCard = new Map(
    productCards.map((card) => [card, readProductVariants(card)])
  );

  const products = new Map();
  productCards.forEach((card) => {
    const baseProduct = productFromCard(card);
    products.set(baseProduct.id, baseProduct);
    (productVariantsByCard.get(card) || []).forEach((variant) => {
      if (!variant?.id || variant.inquiryOnly) return;
      products.set(String(variant.id), {
        ...baseProduct,
        id: String(variant.id),
        name: String(variant.name || baseProduct.name),
        variant: String(variant.unit || baseProduct.variant),
        price: Number(variant.price || 0),
        mrp: Number(variant.mrp || variant.price || baseProduct.mrp || 0),
        image: String(variant.image || baseProduct.image),
        badge: String(variant.badge || baseProduct.badge || "Makhana"),
        secondaryTitle: String(variant.secondaryTitle || baseProduct.secondaryTitle || baseProduct.name),
      });
    });
  });
  const cart = restoreCart();

  function money(value) {
    return `Rs ${Number(value || 0).toLocaleString("en-IN")}`;
  }

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function makeCheckoutToken() {
    if (window.crypto?.randomUUID) return window.crypto.randomUUID();
    const random = Math.random().toString(36).slice(2);
    return `checkout_${Date.now().toString(36)}_${random}`;
  }

  function restoreCart() {
    const restored = new Map();
    try {
      const saved = JSON.parse(window.localStorage.getItem(CART_STORAGE_KEY) || "[]");
      if (!Array.isArray(saved)) return restored;
      saved.forEach((item) => {
        const product = products.get(String(item?.id || ""));
        const quantity = Math.min(50, Math.max(0, Number(item?.quantity || 0)));
        if (product && quantity > 0) restored.set(product.id, { ...product, quantity });
      });
    } catch (error) {
      window.localStorage.removeItem(CART_STORAGE_KEY);
    }
    return restored;
  }

  function persistCart() {
    try {
      const saved = Array.from(cart.values()).map(({ id, quantity }) => ({ id, quantity }));
      window.localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(saved));
    } catch (error) {
      // The cart still works when browser storage is unavailable.
    }
  }

  function selectedPaymentMethod() {
    return orderForm?.querySelector("input[name='payment_method']:checked")?.value || "cod";
  }

  function selectedCoupon() {
    return (config.couponOffers || []).find((offer) => offer.code === appliedCouponCode) || null;
  }

  function totals() {
    const items = Array.from(cart.values());
    const count = items.reduce((sum, item) => sum + item.quantity, 0);
    const subtotal = items.reduce((sum, item) => sum + item.quantity * item.price, 0);
    const coupon = selectedCoupon();
    const couponEligible = Boolean(coupon && subtotal >= Number(coupon.minimum_subtotal || 0));
    let couponDiscount = 0;

    if (couponEligible && Number(coupon.rate_bps || 0) > 0) {
      couponDiscount = Math.round(subtotal * Number(coupon.rate_bps) / 10000);
      const maxDiscount = Number(coupon.max_discount || 0);
      if (maxDiscount > 0) couponDiscount = Math.min(couponDiscount, maxDiscount);
    }

    const onlineDiscount = (
      selectedPaymentMethod() === "razorpay" &&
      config.razorpayEnabled &&
      subtotal >= ONLINE_PAYMENT_MINIMUM_SUBTOTAL
    ) ? ONLINE_PAYMENT_DISCOUNT : 0;
    const discount = Math.min(subtotal, couponDiscount + onlineDiscount);
    const freeDelivery = subtotal >= DELIVERY_FREE_ABOVE || (couponEligible && coupon.waives_delivery);
    const delivery = count && !freeDelivery ? DELIVERY_CHARGE : 0;

    return {
      count,
      subtotal,
      coupon,
      couponEligible,
      discount,
      delivery,
      total: subtotal - discount + delivery,
    };
  }

  function showToast(message) {
    if (!toast || !message) return;
    window.clearTimeout(toastTimer);
    toast.textContent = message;
    toast.classList.add("is-visible");
    toastTimer = window.setTimeout(() => {
      toast.classList.remove("is-visible");
    }, 2200);
  }

  function syncHeader() {
    siteHeader?.classList.toggle("is-scrolled", window.scrollY > 28);
  }

  function closeMenu() {
    nav?.classList.remove("is-open");
    menuToggle?.setAttribute("aria-expanded", "false");
    document.body.classList.remove("menu-open");
  }

  function toggleMenu() {
    const open = !nav?.classList.contains("is-open");
    nav?.classList.toggle("is-open", open);
    menuToggle?.setAttribute("aria-expanded", open ? "true" : "false");
    document.body.classList.toggle("menu-open", open);
  }

  function showHeroSlide(index) {
    if (!heroSlides.length) return;
    activeHeroSlide = (index + heroSlides.length) % heroSlides.length;
    hero.dataset.activeSlide = String(activeHeroSlide);
    heroSlides.forEach((slide, slideIndex) => {
      const active = slideIndex === activeHeroSlide;
      slide.classList.toggle("is-active", active);
      slide.setAttribute("aria-hidden", active ? "false" : "true");
    });
    heroDots.forEach((dot, dotIndex) => {
      dot.setAttribute("aria-current", dotIndex === activeHeroSlide ? "true" : "false");
    });
  }

  function stopHeroAutoplay() {
    window.clearInterval(heroTimer);
    heroTimer = null;
  }

  function startHeroAutoplay() {
    stopHeroAutoplay();
    if (heroSlides.length < 2 || reduceMotion.matches || document.hidden) return;
    heroTimer = window.setInterval(() => showHeroSlide(activeHeroSlide + 1), 5600);
  }

  function selectHeroSlide(index) {
    showHeroSlide(index);
    startHeroAutoplay();
  }

  function syncProductQuantityDisplays() {
    document.querySelectorAll("[data-feature-quantity]").forEach((node) => {
      const quantity = cart.get(node.dataset.featureQuantity)?.quantity || 0;
      node.textContent = String(quantity);
    });
    document.querySelectorAll("[data-feature-add-label]").forEach((node) => {
      const quantity = cart.get(node.dataset.featureAddLabel)?.quantity || 0;
      node.textContent = quantity > 0 ? "Go to Cart" : "Add to Bag";
    });
  }

  function setProductVariant(card, productId) {
    const variants = productVariantsByCard.get(card) || [];
    const variant = variants.find((item) => String(item?.id || "") === String(productId || ""));
    if (!variant) return;

    const inquiryOnly = Boolean(variant.inquiryOnly);
    const productMedia = card.querySelector(".product-media");
    const productImage = card.querySelector("[data-product-image]");
    const title = card.querySelector("[data-product-title]");
    const kicker = card.querySelector("[data-product-kicker]");
    const subtitle = card.querySelector("[data-product-subtitle]");
    const description = card.querySelector("[data-product-description]");
    const price = card.querySelector("[data-product-price]");
    const unit = card.querySelector("[data-product-unit]");
    const highlights = card.querySelector("[data-product-highlights]");
    const actions = card.querySelector("[data-product-actions]");
    const stepper = actions?.querySelector(".product-stepper");
    const addButton = actions?.querySelector("[data-add-product]");
    const addLabel = actions?.querySelector("[data-feature-add-label]");
    const buyNowButton = actions?.querySelector("[data-buy-now]");
    const enquiryButton = actions?.querySelector("[data-product-enquiry]");

    card.dataset.id = String(variant.id || "");
    card.dataset.name = String(variant.name || "Naivedyam Makhana");
    card.dataset.variant = String(variant.unit || "");
    card.dataset.price = String(variant.price || 0);
    card.dataset.mrp = String(variant.mrp || variant.price || 0);
    card.dataset.image = String(variant.image || "");
    card.dataset.cartBadge = String(variant.badge || "Makhana");
    card.dataset.secondaryTitle = String(variant.secondaryTitle || variant.name || "Naivedyam Makhana");

    if (productImage) {
      productImage.src = String(variant.image || productImage.src);
      productImage.alt = String(variant.imageAlt || variant.name || "Naivedyam Makhana");
      productImage.width = Number(variant.imageWidth || productImage.width || 1024);
      productImage.height = Number(variant.imageHeight || productImage.height || 1024);
    }
    productMedia?.classList.toggle("product-media--one-kg", String(variant.id).endsWith("-1kg"));
    productMedia?.classList.toggle("product-media--bulk", inquiryOnly);
    productMedia?.classList.toggle("product-media--wide", Number(variant.imageWidth || 0) > 700);
    if (title) title.textContent = String(variant.displayTitle || variant.name || "Naivedyam Makhana");
    if (kicker) kicker.textContent = String(variant.kicker || "");
    if (subtitle) subtitle.textContent = String(variant.subtitle || "");
    if (description) description.textContent = String(variant.details || "");
    if (price) price.textContent = String(variant.priceLabel || money(variant.price));
    if (unit) unit.textContent = String(variant.unit || "");
    if (highlights) {
      highlights.innerHTML = (Array.isArray(variant.highlights) ? variant.highlights : [])
        .map((highlight) => `<li>${escapeHtml(highlight)}</li>`)
        .join("");
    }

    card.querySelectorAll("[data-product-variant]").forEach((button) => {
      const selected = button.dataset.productVariant === String(variant.id);
      button.classList.toggle("is-selected", selected);
      button.setAttribute("aria-pressed", selected ? "true" : "false");
    });

    if (stepper) {
      stepper.hidden = inquiryOnly;
      stepper.setAttribute("aria-label", `${variant.displayTitle || variant.name || "Naivedyam Makhana"} ${variant.unit || ""} quantity`.trim());
    }
    if (addButton) {
      addButton.hidden = inquiryOnly;
      addButton.dataset.addProduct = String(variant.id || "");
    }
    if (addLabel) addLabel.dataset.featureAddLabel = String(variant.id || "");
    if (buyNowButton) {
      buyNowButton.hidden = inquiryOnly;
      buyNowButton.dataset.buyNow = String(variant.id || "");
    }
    [
      ["[data-feature-minus]", "featureMinus", "Decrease"],
      ["[data-feature-plus]", "featurePlus", "Increase"],
    ].forEach(([selector, datasetName, action]) => {
      const button = actions?.querySelector(selector);
      if (!button) return;
      button.dataset[datasetName] = String(variant.id || "");
      button.setAttribute("aria-label", `${action} ${variant.displayTitle || variant.name || "Naivedyam Makhana"}`);
    });
    const quantity = actions?.querySelector("[data-feature-quantity]");
    if (quantity) quantity.dataset.featureQuantity = String(variant.id || "");
    if (enquiryButton) {
      enquiryButton.hidden = !inquiryOnly;
      enquiryButton.href = inquiryOnly ? String(variant.inquiryUrl || "https://wa.me/919835496666") : "#";
    }

    syncProductQuantityDisplays();
  }

  function renderCartItems() {
    if (!cartItemsNode) return;
    if (!cart.size) {
      cartItemsNode.innerHTML = `
        <div class="empty-cart">
          <div>
            <svg viewBox="0 0 120 120" width="74" height="74" fill="none" aria-hidden="true">
              <rect x="20" y="40" width="80" height="65" rx="6" stroke="currentColor" stroke-width="2" fill="currentColor" opacity="0.07"/>
              <path d="M40 40Q40 20 60 20q20 0 20 20" stroke="currentColor" stroke-width="2"/>
            </svg>
            <strong>Your bag is empty</strong>
            <p>Add a Naivedyam pack, then finish delivery and payment here.</p>
            <button class="text-button" type="button" data-add-more>Shop products</button>
          </div>
        </div>`;
      return;
    }

    cartItemsNode.innerHTML = Array.from(cart.values()).map((item) => `
      <article class="cart-line">
        <img src="${escapeHtml(item.image)}" alt="${escapeHtml(item.name)}" width="94" height="98">
        <div class="cart-line-info">
          <strong>${escapeHtml(item.name)}</strong>
          <small>${escapeHtml(item.variant)} · ${escapeHtml(item.badge || "Makhana")}</small>
          <div class="cart-line-actions">
            <div class="mini-stepper">
              <button type="button" data-cart-minus="${escapeHtml(item.id)}" aria-label="Decrease ${escapeHtml(item.name)}">-</button>
              <span>${item.quantity}</span>
              <button type="button" data-cart-plus="${escapeHtml(item.id)}" aria-label="Increase ${escapeHtml(item.name)}">+</button>
            </div>
            <button class="line-remove" type="button" data-cart-remove="${escapeHtml(item.id)}" aria-label="Remove ${escapeHtml(item.name)}" title="Remove">
              <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3m3 0-1 14H7L6 7m4 4v6m4-6v6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
            </button>
          </div>
        </div>
        <strong class="cart-line-price">${money(item.price * item.quantity)}</strong>
      </article>
    `).join("");
  }

  function renderCart() {
    const { count, subtotal, coupon, couponEligible, discount, delivery, total } = totals();
    if (cartCount) cartCount.textContent = String(count);
    if (summarySubtitle) {
      summarySubtitle.textContent = count ? `${count} ${count === 1 ? "item" : "items"}` : "Cart is empty";
    }
    if (summarySubtotal) summarySubtotal.textContent = money(subtotal);
    if (summaryDelivery) summaryDelivery.textContent = delivery ? money(delivery) : "Free";
    if (summaryTotal) summaryTotal.textContent = money(total);
    if (savingsLine && summarySavings) {
      savingsLine.hidden = discount <= 0;
      summarySavings.textContent = `-${money(discount)}`;
    }

    couponButtons.forEach((button) => {
      const applied = button.dataset.couponApply === appliedCouponCode;
      button.classList.toggle("is-applied", applied);
      button.setAttribute("aria-pressed", applied ? "true" : "false");
      const action = button.querySelector("em");
      if (action) action.textContent = applied ? "Applied" : "Apply";
    });

    if (couponInput) {
      couponInput.value = JSON.stringify(coupon && couponEligible ? [coupon.code] : []);
    }
    if (couponFeedback) {
      if (!count) couponFeedback.textContent = "Add a product to use a coupon.";
      else if (coupon && couponEligible) couponFeedback.textContent = `${coupon.code} applied to this order.`;
      else if (coupon) couponFeedback.textContent = `${coupon.code} needs a minimum order of ${money(coupon.minimum_subtotal)}.`;
      else couponFeedback.textContent = "Select an offer for this order.";
    }

    if (cartInput) {
      cartInput.value = JSON.stringify(
        Array.from(cart.values()).map(({ id, quantity }) => ({ id, quantity }))
      );
    }

    if (submitButton && !checkoutBusy) {
      submitButton.disabled = count === 0;
      if (!count) submitButton.textContent = "Place order";
      else if (config.customerLoginRequired && !config.authenticated) submitButton.textContent = "Login to place order";
      else if (selectedPaymentMethod() === "razorpay" && config.razorpayEnabled) submitButton.textContent = `Pay ${money(total)}`;
      else submitButton.textContent = `Place order · ${money(total)}`;
    }

    syncProductQuantityDisplays();
    renderCartItems();
    persistCart();
  }

  function addToCart(id, quantity = 1) {
    const product = products.get(id);
    if (!product) return;
    const existing = cart.get(id);
    cart.set(id, { ...product, quantity: Math.min(50, (existing?.quantity || 0) + quantity) });
    renderCart();
    showToast(`${product.name} added to your bag`);
  }

  function setItemQuantity(id, quantity) {
    const product = products.get(id);
    if (!product) return;
    if (quantity <= 0) cart.delete(id);
    else cart.set(id, { ...product, quantity: Math.min(50, quantity) });
    renderCart();
  }

  function setDrawerOpen(open) {
    drawer?.classList.toggle("is-open", open);
    drawerBackdrop?.classList.toggle("is-open", open);
    drawer?.setAttribute("aria-hidden", open ? "false" : "true");
    document.body.classList.toggle("drawer-open", open);
    if (!open) orderResult?.classList.remove("error");
  }

  function setAccountOpen(open) {
    accountModal?.classList.toggle("is-open", open);
    accountModal?.setAttribute("aria-hidden", open ? "false" : "true");
    document.body.classList.toggle("modal-open", open);
  }

  function setOrderSuccessOpen(open) {
    orderSuccessModal?.classList.toggle("is-open", open);
    orderSuccessModal?.setAttribute("aria-hidden", open ? "false" : "true");
    document.body.classList.toggle("order-success-open", open);
    if (open) {
      window.setTimeout(() => orderSuccessCloseButton?.focus(), 0);
    } else if (orderSuccessReturnFocus?.isConnected) {
      orderSuccessReturnFocus.focus();
    }
  }

  function openOrderSuccessModal(order) {
    if (!orderSuccessModal) return;
    orderSuccessReturnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    if (orderSuccessId) orderSuccessId.textContent = order?.["Order ID"] || "Confirmed";
    setDrawerOpen(false);
    setOrderSuccessOpen(true);
  }

  function openAccountModal(message = "", showHistory = false) {
    if (message && accountCopy) accountCopy.textContent = message;
    setAccountOpen(true);
    if (showHistory) showOrderHistory();
  }

  function showOrderHistory() {
    orderHistoryPanel?.classList.add("is-open");
    if (!config.authenticated) {
      if (orderHistoryStatus) orderHistoryStatus.textContent = "Continue with Google to see your previous orders.";
      return;
    }
    loadOrderHistory();
  }

  function renderOrderHistory(orders) {
    if (!orderHistoryList || !orderHistoryStatus) return;
    if (!orders.length) {
      orderHistoryStatus.textContent = "No previous orders are linked to this Google account yet.";
      orderHistoryList.innerHTML = "";
      return;
    }
    orderHistoryStatus.textContent = `${orders.length} ${orders.length === 1 ? "order" : "orders"} found.`;
    orderHistoryList.innerHTML = orders.map((order) => `
      <article class="history-order">
        <div>
          <strong>${escapeHtml(order.order_id || "Order")}</strong>
          <small>${escapeHtml(order.product || "Naivedyam Makhana")} · ${money(order.total_amount || 0)}</small>
        </div>
        <em>${escapeHtml(order.order_status || "Received")}</em>
      </article>
    `).join("");
  }

  async function loadOrderHistory(force = false) {
    if (!config.authenticated || !orderHistoryStatus || !orderHistoryList) return;
    const now = Date.now();
    if (!force && loadOrderHistory.cache && now - loadOrderHistory.cache.fetchedAt < 30000) {
      renderOrderHistory(loadOrderHistory.cache.orders);
      return;
    }
    if (loadOrderHistory.pending) return;
    loadOrderHistory.pending = true;
    orderHistoryStatus.textContent = "Loading your orders...";
    orderHistoryList.innerHTML = "";

    try {
      const response = await fetch("/api/me/orders", { headers: { Accept: "application/json" } });
      const data = await parseResponse(response);
      if (!response.ok || !data.ok) throw new Error(data.error || "Order history could not be loaded.");
      const orders = Array.isArray(data.orders) ? data.orders : [];
      loadOrderHistory.cache = { fetchedAt: now, orders };
      renderOrderHistory(orders);
    } catch (error) {
      orderHistoryStatus.textContent = error.message || "Order history could not be loaded.";
    } finally {
      loadOrderHistory.pending = false;
    }
  }

  function rememberOrderForHistory(order) {
    if (!order?.["Order ID"]) return;
    const historyOrder = {
      order_id: order["Order ID"],
      product: order.Product || "",
      total_amount: order["Total Amount"] || "",
      order_status: order["Order Status"] || "Received",
    };
    const existing = loadOrderHistory.cache?.orders || [];
    loadOrderHistory.cache = {
      fetchedAt: Date.now(),
      orders: [historyOrder, ...existing.filter((item) => item.order_id !== historyOrder.order_id)],
    };
  }

  function buildGoogleLoginUrl() {
    const target = new URL(config.googleLoginUrl || "/auth/google", window.location.origin);
    target.searchParams.set("next", `${window.location.pathname}${window.location.search}`);
    return target.toString();
  }

  async function parseResponse(response) {
    const text = await response.text();
    try {
      return text ? JSON.parse(text) : {};
    } catch (error) {
      return { ok: false, error: text.slice(0, 180) || "Server returned an unexpected response." };
    }
  }

  function buildPayload() {
    const payload = Object.fromEntries(new FormData(orderForm).entries());
    payload.cart_items = cartInput?.value || "[]";
    payload.coupon_codes = couponInput?.value || "[]";
    payload.payment_method = selectedPaymentMethod();
    payload.checkout_token = checkoutToken;
    payload.source = "Website";
    return payload;
  }

  function handleAuthError(data) {
    if (!data?.auth_required) return false;
    const message = data.error || "Please login with Google before placing your order.";
    if (orderResult) {
      orderResult.textContent = message;
      orderResult.classList.add("error");
    }
    openAccountModal(message);
    return true;
  }

  function loadRazorpayCheckout() {
    if (!config.razorpayEnabled) {
      return Promise.reject(new Error("Online payment is not available right now."));
    }
    if (window.Razorpay) return Promise.resolve();
    if (!razorpayCheckoutPromise) {
      razorpayCheckoutPromise = new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://checkout.razorpay.com/v1/checkout.js";
        script.async = true;
        script.onload = resolve;
        script.onerror = () => {
          razorpayCheckoutPromise = null;
          reject(new Error("Razorpay could not be loaded. Please try COD."));
        };
        document.head.appendChild(script);
      });
    }
    return razorpayCheckoutPromise;
  }

  async function submitCodOrder(payload) {
    const response = await fetch("/api/orders", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await parseResponse(response);
    if (handleAuthError(data)) throw new Error("");
    if (!response.ok || !data.ok) {
      const errors = data.errors ? Object.values(data.errors).join(" ") : "";
      throw new Error(errors || data.error || "Order could not be placed.");
    }
    return data;
  }

  async function submitRazorpayOrder(payload) {
    await loadRazorpayCheckout();
    const orderResponse = await fetch("/api/payments/razorpay/order", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    });
    const orderData = await parseResponse(orderResponse);
    if (handleAuthError(orderData)) throw new Error("");
    if (orderData.duplicate && orderData.order) return orderData;
    if (!orderResponse.ok || !orderData.ok) {
      const errors = orderData.errors ? Object.values(orderData.errors).join(" ") : "";
      throw new Error(errors || orderData.error || "Razorpay order could not be created.");
    }

    return new Promise((resolve, reject) => {
      const checkout = new window.Razorpay({
        key: orderData.key_id || config.razorpayKeyId,
        amount: orderData.amount,
        currency: orderData.currency || "INR",
        name: "Pulps & Leaves",
        description: "Naivedyam Makhana",
        order_id: orderData.order_id,
        prefill: orderData.customer || {},
        theme: { color: "#123f2a" },
        handler: async (paymentResponse) => {
          try {
            const verifyResponse = await fetch("/api/payments/razorpay/verify", {
              method: "POST",
              headers: { "Content-Type": "application/json", Accept: "application/json" },
              body: JSON.stringify({
                razorpay_order_id: paymentResponse.razorpay_order_id,
                razorpay_payment_id: paymentResponse.razorpay_payment_id,
                razorpay_signature: paymentResponse.razorpay_signature,
                verification_token: orderData.verification_token,
              }),
            });
            const verifyData = await parseResponse(verifyResponse);
            if (handleAuthError(verifyData)) throw new Error("");
            if (!verifyResponse.ok || !verifyData.ok) {
              const errors = verifyData.errors ? Object.values(verifyData.errors).join(" ") : "";
              throw new Error(errors || verifyData.error || "Payment could not be verified.");
            }
            resolve(verifyData);
          } catch (error) {
            reject(error);
          }
        },
        modal: {
          ondismiss: () => reject(new Error("Payment was cancelled.")),
        },
      });
      checkout.open();
    });
  }

  function restoreCustomerFields() {
    if (!orderForm || !config.customer) return;
    const fields = {
      name: config.customer.name || "",
      phone: config.customer.phone || "",
      city: config.customer.city || "",
      address: config.customer.address || "",
    };
    Object.entries(fields).forEach(([name, value]) => {
      const field = orderForm.elements[name];
      if (field && !field.disabled && value) field.value = value;
    });
  }

  function handleOrderSuccess(order, message) {
    const orderId = order?.["Order ID"] || "";
    if (orderResult) {
      orderResult.textContent = `${message}. Order ID: ${orderId || "received"}.`;
      orderResult.classList.remove("error");
    }
    rememberOrderForHistory(order);
    cart.clear();
    appliedCouponCode = "";
    checkoutToken = makeCheckoutToken();
    orderForm?.reset();
    restoreCustomerFields();
    renderCart();
    showToast(`${message}${orderId ? ` · ${orderId}` : ""}`);
    openOrderSuccessModal(order);
  }

  async function submitOrder(event) {
    event.preventDefault();
    if (checkoutBusy) return;
    renderCart();
    if (!cart.size) {
      if (orderResult) {
        orderResult.textContent = "Please add a Naivedyam pack before placing your order.";
        orderResult.classList.add("error");
      }
      return;
    }
    if (config.customerLoginRequired && !config.authenticated) {
      openAccountModal("Please continue with Google before placing your order.");
      return;
    }
    if (!orderForm.reportValidity()) return;

    checkoutBusy = true;
    if (orderResult) {
      orderResult.textContent = "";
      orderResult.classList.remove("error");
    }
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = selectedPaymentMethod() === "razorpay" ? "Opening secure payment..." : "Placing your order...";
    }
    const payload = buildPayload();

    try {
      const data = selectedPaymentMethod() === "razorpay" && config.razorpayEnabled
        ? await submitRazorpayOrder(payload)
        : await submitCodOrder(payload);
      handleOrderSuccess(data.order || {}, data.duplicate ? "Order already placed" : "Order placed");
    } catch (error) {
      if (error.message && orderResult) {
        orderResult.textContent = error.message;
        orderResult.classList.add("error");
      }
    } finally {
      checkoutBusy = false;
      renderCart();
    }
  }

  window.addEventListener("scroll", syncHeader, { passive: true });
  syncHeader();

  menuToggle?.addEventListener("click", toggleMenu);
  nav?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));

  document.querySelector("[data-hero-prev]")?.addEventListener("click", () => selectHeroSlide(activeHeroSlide - 1));
  document.querySelector("[data-hero-next]")?.addEventListener("click", () => selectHeroSlide(activeHeroSlide + 1));
  heroDots.forEach((dot) => {
    dot.addEventListener("click", () => selectHeroSlide(Number(dot.dataset.heroDot || 0)));
  });
  hero?.addEventListener("touchstart", (event) => {
    heroTouchStartX = event.changedTouches[0]?.clientX ?? null;
    stopHeroAutoplay();
  }, { passive: true });
  hero?.addEventListener("touchend", (event) => {
    const endX = event.changedTouches[0]?.clientX;
    if (heroTouchStartX !== null && typeof endX === "number") {
      const delta = endX - heroTouchStartX;
      if (Math.abs(delta) > 48) showHeroSlide(activeHeroSlide + (delta < 0 ? 1 : -1));
    }
    heroTouchStartX = null;
    startHeroAutoplay();
  }, { passive: true });

  const finePointer = window.matchMedia("(pointer: fine)");
  if (hero && finePointer.matches) {
    const heroProducts = Array.from(hero.querySelectorAll(".hero-product"));
    hero.addEventListener("pointermove", (event) => {
      if (reduceMotion.matches) return;
      const bounds = hero.getBoundingClientRect();
      const shiftX = (((event.clientX - bounds.left) / bounds.width) - 0.5) * 14;
      const shiftY = (((event.clientY - bounds.top) / bounds.height) - 0.5) * 10;
      heroProducts.forEach((product) => {
        product.style.setProperty("--hero-shift-x", `${shiftX.toFixed(2)}px`);
        product.style.setProperty("--hero-shift-y", `${shiftY.toFixed(2)}px`);
      });
    });
    hero.addEventListener("pointerenter", stopHeroAutoplay);
    hero.addEventListener("pointerleave", () => {
      heroProducts.forEach((product) => {
        product.style.setProperty("--hero-shift-x", "0px");
        product.style.setProperty("--hero-shift-y", "0px");
      });
      startHeroAutoplay();
    });
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stopHeroAutoplay();
    else startHeroAutoplay();
  });
  reduceMotion.addEventListener?.("change", startHeroAutoplay);
  showHeroSlide(0);
  startHeroAutoplay();

  const revealItems = Array.from(document.querySelectorAll("[data-reveal]"));
  if ("IntersectionObserver" in window && !reduceMotion.matches) {
    const revealObserver = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      });
    }, { threshold: 0.14, rootMargin: "0px 0px -7% 0px" });
    revealItems.forEach((item) => revealObserver.observe(item));

    const origin = document.querySelector("[data-origin]");
    if (origin) {
      const originObserver = new IntersectionObserver((entries) => {
        entries.forEach((entry) => entry.target.classList.toggle("is-in-view", entry.isIntersecting));
      }, { threshold: 0.18 });
      originObserver.observe(origin);
    }
  } else {
    revealItems.forEach((item) => item.classList.add("is-visible"));
  }

  document.addEventListener("click", (event) => {
    const addButton = event.target.closest("[data-add-product]");
    const openCartButton = event.target.closest("[data-cart-open]");
    const closeCartButton = event.target.closest("[data-cart-close]");
    const addMoreButton = event.target.closest("[data-add-more]");
    const minusButton = event.target.closest("[data-cart-minus]");
    const plusButton = event.target.closest("[data-cart-plus]");
    const removeButton = event.target.closest("[data-cart-remove]");
    const featureMinus = event.target.closest("[data-feature-minus]");
    const featurePlus = event.target.closest("[data-feature-plus]");
    const buyNowButton = event.target.closest("[data-buy-now]");
    const accountOpen = event.target.closest("[data-account-open]");
    const accountClose = event.target.closest("[data-account-close]");
    const orderSuccessClose = event.target.closest("[data-order-success-close]");
    const productVariantButton = event.target.closest("[data-product-variant]");

    if (addButton) {
      const productId = addButton.dataset.addProduct;
      if ((cart.get(productId)?.quantity || 0) > 0) setDrawerOpen(true);
      else addToCart(productId, Number(addButton.dataset.addQuantity || 1));
    }
    if (openCartButton) setDrawerOpen(true);
    if (closeCartButton) setDrawerOpen(false);
    if (addMoreButton) {
      setDrawerOpen(false);
      document.querySelector("#shop")?.scrollIntoView({ behavior: reduceMotion.matches ? "auto" : "smooth" });
    }
    if (minusButton) setItemQuantity(minusButton.dataset.cartMinus, (cart.get(minusButton.dataset.cartMinus)?.quantity || 0) - 1);
    if (plusButton) setItemQuantity(plusButton.dataset.cartPlus, (cart.get(plusButton.dataset.cartPlus)?.quantity || 0) + 1);
    if (removeButton) setItemQuantity(removeButton.dataset.cartRemove, 0);
    if (featureMinus) setItemQuantity(featureMinus.dataset.featureMinus, (cart.get(featureMinus.dataset.featureMinus)?.quantity || 0) - 1);
    if (featurePlus) setItemQuantity(featurePlus.dataset.featurePlus, (cart.get(featurePlus.dataset.featurePlus)?.quantity || 0) + 1);
    if (buyNowButton) {
      const productId = buyNowButton.dataset.buyNow;
      if ((cart.get(productId)?.quantity || 0) === 0) addToCart(productId);
      setDrawerOpen(true);
    }
    if (accountOpen) openAccountModal();
    if (accountClose) setAccountOpen(false);
    if (orderSuccessClose) setOrderSuccessOpen(false);
    if (productVariantButton) {
      const productCard = productVariantButton.closest("[data-product]");
      if (productCard) setProductVariant(productCard, productVariantButton.dataset.productVariant);
    }
  });

  drawerBackdrop?.addEventListener("click", () => setDrawerOpen(false));
  accountModal?.addEventListener("click", (event) => {
    if (event.target === accountModal) setAccountOpen(false);
  });
  orderSuccessModal?.addEventListener("click", (event) => {
    if (event.target === orderSuccessModal) setOrderSuccessOpen(false);
  });

  couponButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const code = button.dataset.couponApply || "";
      appliedCouponCode = appliedCouponCode === code ? "" : code;
      renderCart();
    });
  });
  paymentInputs.forEach((input) => input.addEventListener("change", renderCart));

  addressMapButton?.addEventListener("click", () => {
    const address = String(deliveryAddress?.value || "").trim();
    if (!address) {
      deliveryAddress?.focus();
      showToast("Enter your delivery address first.");
      return;
    }
    const citySelect = orderForm?.elements.city;
    const city = citySelect?.selectedOptions?.[0]?.textContent?.trim() || "";
    const query = [address, city, "India"].filter(Boolean).join(", ");
    const mapWindow = window.open(
      `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(query)}`,
      "_blank",
      "noopener,noreferrer"
    );
    if (mapWindow) mapWindow.opener = null;
  });

  googleLoginButton?.addEventListener("click", () => {
    if (!config.googleLoginEnabled) {
      if (accountCopy) accountCopy.textContent = "Google login is not configured in this local preview.";
      return;
    }
    window.location.assign(buildGoogleLoginUrl());
  });

  orderHistoryButton?.addEventListener("click", showOrderHistory);
  logoutButton?.addEventListener("click", async () => {
    logoutButton.disabled = true;
    try {
      const response = await fetch("/auth/logout", {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error("Could not sign out.");
      window.location.assign("/");
    } catch (error) {
      logoutButton.disabled = false;
      showToast(error.message || "Could not sign out.");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (orderSuccessModal?.classList.contains("is-open")) setOrderSuccessOpen(false);
    else if (accountModal?.classList.contains("is-open")) setAccountOpen(false);
    else if (drawer?.classList.contains("is-open")) setDrawerOpen(false);
    else closeMenu();
  });

  orderForm?.addEventListener("submit", submitOrder);

  const searchParams = new URLSearchParams(window.location.search);
  if (searchParams.has("account_error")) {
    openAccountModal("Google sign-in could not be completed. Please try again.");
  }
  if (searchParams.get("account") === "1") {
    openAccountModal();
  }
  if (window.location.hash === "#orders") {
    openAccountModal("", true);
  }

  restoreCustomerFields();
  renderCart();
})();
