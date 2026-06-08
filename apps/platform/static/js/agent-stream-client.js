/**
 * AgentStreamClient - 博客 AI 写作助手的流式调用客户端
 */
class AgentStreamClient {
    constructor(baseUrl = "") {
        this.baseUrl = baseUrl.replace(/\/$/, "");
    }

    async stream(endpoint, payload, callbacks = {}) {
        const { onMeta, onChunk, onDone, onError } = callbacks;

        try {
            const resp = await fetch(`${this.baseUrl}${endpoint}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    Accept: "text/event-stream",
                },
                body: JSON.stringify(payload),
            });

            if (!resp.ok) {
                const errText = await resp.text();
                throw new Error(`HTTP ${resp.status}: ${errText}`);
            }

            const reader = resp.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const parts = buffer.split("\n\n");
                buffer = parts.pop();

                for (const part of parts) {
                    const msg = this._parseSsePart(part);
                    if (!msg) continue;

                    switch (msg.type) {
                        case "meta":
                            onMeta && onMeta(msg.data);
                            break;
                        case "content":
                            onChunk && onChunk(msg.data);
                            break;
                        case "done":
                            onDone && onDone();
                            return;
                        case "error":
                            onError && onError(new Error(msg.data));
                            return;
                    }
                }
            }

            onDone && onDone();
        } catch (err) {
            onError && onError(err);
        }
    }

    _parseSsePart(part) {
        const lines = part.split("\n").map((l) => l.trim());
        for (const line of lines) {
            if (line.startsWith("data: ")) {
                try {
                    return JSON.parse(line.slice(6));
                } catch {
                    return { type: "content", data: line.slice(6) };
                }
            }
        }
        return null;
    }

    streamOutline(topic, style = "tutorial", callbacks) {
        return this.stream("/ai/outline/stream", { topic, style }, callbacks);
    }

    streamPolish(text, tone = "professional", callbacks) {
        return this.stream("/ai/polish/stream", { text, tone }, callbacks);
    }

    streamAnalyze(callbacks) {
        return this.stream("/ai/analyze/stream", {}, callbacks);
    }

    streamRecommend(techStack = null, callbacks) {
        return this.stream("/ai/recommend/stream", { tech_stack: techStack }, callbacks);
    }

    streamDraft(topic, style = "tutorial", callbacks) {
        return this.stream("/ai/draft/stream", { topic, style }, callbacks);
    }
}

if (typeof module !== "undefined" && module.exports) {
    module.exports = { AgentStreamClient };
}
