(function () {
  function maskStructuredValue(value, type, mode, keepChars) {
    const text = value == null ? "" : String(value);
    if (!text || mode === "none") return text;
    if (mode === "full" || Array.from(text).length === 1) {
      return "*".repeat(Array.from(text).length);
    }

    const characters = Array.from(text);
    const requested = Number.parseInt(keepChars, 10) || 1;
    const visibleCount = characters.length > requested ? requested : characters.length - 1;
    const hidden = "*".repeat(characters.length - visibleCount);
    if (mode === "keep_start") {
      return characters.slice(0, visibleCount).join("") + hidden;
    }
    if (mode === "keep_end") {
      return hidden + characters.slice(-visibleCount).join("");
    }
    throw new Error("不支援的遮罩模式");
  }

  function redirectAfterRecord() {
    const params = new URLSearchParams(window.location.search);
    const redirectUrl = params.get("redirect_url");
    if (redirectUrl === "self") {
      window.location.reload();
    } else if (redirectUrl === "password") {
      window.location.href = `${API_BASE_PATH}/password-wrong`;
    } else if (redirectUrl) {
      window.location.href = redirectUrl;
    } else {
      window.location.href = `${API_BASE_PATH}/warning`;
    }
  }

  if (typeof module !== "undefined") {
    module.exports = { maskStructuredValue };
  }

  if (typeof document === "undefined") return;
  const form = document.getElementById("structured-form");
  if (!form) return;

  form.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!form.reportValidity()) return;

    const inputs = Array.from(form.querySelectorAll("[data-structured-field-id]"));
    const fields = inputs.map((input) => ({
      id: input.dataset.structuredFieldId,
      value: maskStructuredValue(
        input.value,
        input.dataset.fieldType,
        input.dataset.maskMode,
        input.dataset.keepChars
      ),
    }));
    const submitButton = form.querySelector('[type="submit"]');
    if (submitButton) submitButton.disabled = true;

    try {
      const response = await fetch(`${API_BASE_PATH}/api/structured-input`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: window.location.href,
          revision: Number.parseInt(form.dataset.specRevision, 10),
          fields,
        }),
      });
      if (!response.ok) {
        const result = await response.json().catch(() => ({}));
        throw new Error(result.detail || "資料送出失敗");
      }
      redirectAfterRecord();
    } catch (error) {
      window.alert(`錯誤：${error.message}`);
      if (submitButton) submitButton.disabled = false;
    }
  });
})();