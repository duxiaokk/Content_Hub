document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("login-form");
    const statusEl = document.getElementById("login-status");
    const submitButton = form?.querySelector('button[type="submit"]');
    const usernameInput = form?.querySelector('input[name="username"]');
    const passwordInput = form?.querySelector('input[name="password"]');
    const rememberInput = form?.querySelector('input[name="remember"]');
    const nextInput = form?.querySelector('input[name="next"]');

    if (!form || !statusEl || !submitButton || !usernameInput || !passwordInput) return;

    const sanitizeNext = (value) => {
        if (!value) return "";
        try {
            const url = new URL(value, window.location.origin);
            return url.origin === window.location.origin ? `${url.pathname}${url.search}${url.hash}` : "";
        } catch {
            return value.startsWith("/") ? value : "";
        }
    };

    const setStatus = (message = "", isError = false) => {
        statusEl.textContent = message;
        statusEl.classList.toggle("is-error", isError);
    };

    const setFieldState = (input, isValid) => {
        input.classList.toggle("is-invalid", !isValid);
        input.setAttribute("aria-invalid", String(!isValid));
    };

    const validate = () => {
        const usernameOk = usernameInput.value.trim().length >= 3;
        const passwordOk = passwordInput.value.trim().length >= 6;
        setFieldState(usernameInput, usernameOk);
        setFieldState(passwordInput, passwordOk);
        return usernameOk && passwordOk;
    };

    const redirectToNext = () => {
        const next = sanitizeNext(nextInput?.value || new URLSearchParams(window.location.search).get("next") || "");
        window.location.href = next || "/";
    };

    usernameInput.addEventListener("input", validate);
    passwordInput.addEventListener("input", validate);
    usernameInput.addEventListener("blur", validate);
    passwordInput.addEventListener("blur", validate);

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        if (!validate()) {
            setStatus("Username must be at least 3 characters and password at least 6.", true);
            return;
        }

        const originalText = submitButton.textContent;
        submitButton.disabled = true;
        setStatus("Signing in...");

        try {
            const formData = new FormData(form);
            formData.set("remember", rememberInput?.checked ? "1" : "0");
            const payload = Object.fromEntries(formData.entries());
            payload.remember = rememberInput?.checked || false;

            const response = await fetch("/login", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                credentials: "same-origin",
                body: JSON.stringify(payload),
            });

            const data = await response.json().catch(() => ({}));
            if (!response.ok) {
                setStatus(data.detail || "Login failed.", true);
                return;
            }

            setStatus("");
            redirectToNext();
        } catch {
            setStatus("Network error. Please try again.", true);
        } finally {
            submitButton.disabled = false;
            submitButton.textContent = originalText;
        }
    });
});
