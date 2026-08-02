/** @odoo-module **/

// Category is derived from the file extension rather than a stored mimetype
// field, since education.lesson.content doesn't keep one — the uploaded
// filename is all we reliably have on both new and saved records.
const EXTENSION_CATEGORY = {
    png: "image", jpg: "image", jpeg: "image", gif: "image", bmp: "image", webp: "image", svg: "image",
    mp4: "video", webm: "video", mov: "video", mkv: "video", avi: "video",
    mp3: "audio", wav: "audio", ogg: "audio", m4a: "audio", aac: "audio", flac: "audio",
    pdf: "pdf",
    txt: "text", csv: "text", md: "text", json: "text",
    doc: "office", docx: "office", xls: "office", xlsx: "office",
    ppt: "office", pptx: "office", odt: "office", ods: "office", odp: "office",
};

function extensionOf(filename) {
    if (!filename) {
        return "";
    }
    const idx = filename.lastIndexOf(".");
    return idx === -1 ? "" : filename.slice(idx + 1).toLowerCase();
}

function isYoutubeUrl(url) {
    return !!url && (url.includes("youtube.com") || url.includes("youtu.be"));
}

function youtubeEmbedUrl(url) {
    let token;
    if (url.includes("youtu.be/")) {
        token = url.split("youtu.be/")[1].split("?")[0];
    } else {
        token = (url.split("v=")[1] || "").split("&")[0];
    }
    return `https://www.youtube.com/embed/${token}`;
}

/**
 * @param {import("@web/model/relational_model/record").Record} record
 * @returns {{available: boolean, reason?: string, category?: string, name?: string, url?: string, downloadUrl?: string}}
 */
export function getPreviewInfo(record) {
    const data = record.data;
    const externalUrl = data.external_url || "";

    // Keyed off content_filename (a light Char field) rather than the heavy
    // content_file binary itself — list views don't load binary payloads by
    // default, but the filename is cheap and reliably fetched, and it's set
    // locally the moment a file is picked, in or out of a saved record.
    if (data.content_filename) {
        if (!record.resId) {
            // Uploaded but not saved yet — there's no server URL to preview
            // from until the record (and its underlying attachment) exists.
            return { available: false, reason: "unsaved" };
        }
        const filename = data.content_filename || data.name || "file";
        const category = EXTENSION_CATEGORY[extensionOf(filename)] || "unsupported";
        const url = `/web/content/education.lesson.content/${record.resId}/content_file/${encodeURIComponent(filename)}`;
        return { available: true, category, name: filename, url, downloadUrl: `${url}?download=true` };
    }

    if (externalUrl) {
        const name = data.name || externalUrl;
        if (isYoutubeUrl(externalUrl)) {
            return { available: true, category: "youtube", name, url: youtubeEmbedUrl(externalUrl), downloadUrl: externalUrl };
        }
        return { available: true, category: "link", name, url: externalUrl, downloadUrl: externalUrl };
    }

    return { available: false, reason: "empty" };
}
