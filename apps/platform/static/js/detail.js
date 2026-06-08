document.addEventListener("DOMContentLoaded", () => {
    const page = document.querySelector(".detail-shell");
    const commentsList = document.getElementById("comments-list");
    const commentForm = document.getElementById("comment-form");
    const likeButton = document.querySelector("[data-like-button]");
    const deleteButton = document.querySelector("[data-delete-button]");

    if (!page || !commentsList) return;

    const postId = page.dataset.postId;
    const isAdmin = page.dataset.isAdmin === "1";
    const likeCountEl = likeButton ? likeButton.querySelector("strong[data-like-count]") : null;

    const getCsrfToken = () => {
        const match = document.cookie.match(/(?:^|; )csrf_token=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    };

    const ensureCsrfToken = async () => {
        const existingToken = getCsrfToken();
        if (existingToken) return existingToken;
        const response = await fetch("/csrf-token", {
            credentials: "same-origin",
        });
        const data = await response.json().catch(() => ({}));
        return data.csrf_token || getCsrfToken();
    };

    const apiFetch = async (url, options = {}) => {
        const headers = new Headers(options.headers || {});
        const method = (options.method || "GET").toUpperCase();
        if (method !== "GET") {
            const csrfToken = await ensureCsrfToken();
            if (csrfToken) {
                headers.set("X-CSRF-Token", csrfToken);
            }
            headers.set("X-Requested-With", "XMLHttpRequest");
        }
        if (options.body && !headers.has("Content-Type")) {
            headers.set("Content-Type", "application/json");
        }

        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers,
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(data.detail || "Request failed");
        }
        return data;
    };

    const setLikeButtonState = (liked, count) => {
        if (!likeButton) return;
        likeButton.classList.toggle("is-active", liked);
        likeButton.setAttribute("aria-pressed", liked ? "true" : "false");
        const label = likeButton.querySelector("[data-like-label]");
        if (label) label.textContent = liked ? "Liked" : "Like";
        if (likeCountEl) likeCountEl.textContent = String(count);
    };

    const escapeHtml = (value) => String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");

    const renderComments = (items) => {
        if (!items.length) {
            commentsList.innerHTML = '<div class="comments-empty">No comments yet.</div>';
            return;
        }

        commentsList.innerHTML = items.map((item) => `
            <article class="comment-item" data-comment-id="${item.id}">
                <div class="comment-item__top">
                    <div class="comment-item__user">${item.username}</div>
                    <div class="comment-item__time">${item.created_at ? new Date(item.created_at).toLocaleString() : ""}</div>
                </div>
                <div class="comment-item__content">${escapeHtml(item.content)}</div>
                <div class="comment-item__actions">
                    <button type="button" class="comment-item__action ${item.liked_by_me ? "is-active" : ""}" data-comment-like="${item.id}">
                        Like <span data-comment-like-count="${item.id}">${item.like_count || 0}</span>
                    </button>
                </div>
            </article>
        `).join("");
    };

    const loadComments = async () => {
        commentsList.innerHTML = '<div class="comments-empty">Loading comments...</div>';
        try {
            const data = await apiFetch(`/posts/${postId}/comments?page=1&page_size=50`);
            renderComments(data.items || []);
        } catch (error) {
            commentsList.innerHTML = `<div class="comments-empty">${error.message}</div>`;
        }
    };

    if (commentForm) {
        commentForm.addEventListener("submit", async (event) => {
            event.preventDefault();
            const textarea = commentForm.querySelector("textarea[name='content']");
            const content = textarea?.value.trim();
            if (!content) return;

            try {
                await apiFetch(`/posts/${postId}/comments`, {
                    method: "POST",
                    body: JSON.stringify({ content }),
                });
                textarea.value = "";
                await loadComments();
            } catch (error) {
                alert(error.message);
            }
        });
    }

    if (likeButton) {
        likeButton.addEventListener("click", async (event) => {
            event.preventDefault();
            try {
                const data = await apiFetch(`/api/v1/posts/${postId}/like`, { method: "POST" });
                setLikeButtonState(!!data.liked, data.count ?? 0);
            } catch (error) {
                alert(error.message);
            }
        });
    }

    if (deleteButton && isAdmin) {
        deleteButton.addEventListener("click", async () => {
            if (!confirm("Delete this post?")) return;
            try {
                await apiFetch(`/api/v1/posts/${postId}`, { method: "DELETE" });
                window.location.href = "/";
            } catch (error) {
                alert(error.message);
            }
        });
    }

    commentsList.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-comment-like]");
        if (!button) return;
        const commentId = button.dataset.commentLike;
        try {
            const data = await apiFetch(`/comments/${commentId}/like`, { method: "POST" });
            const countEl = commentsList.querySelector(`[data-comment-like-count="${commentId}"]`);
            if (countEl) countEl.textContent = data.like_count;
            button.classList.toggle("is-active", !!data.liked);
        } catch (error) {
            alert(error.message);
        }
    });

    setLikeButtonState(page.dataset.liked === "1", Number(page.dataset.likeCount || 0));
    loadComments();
});
