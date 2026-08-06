/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, onWillStart, useState } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

const BLOOM_LABELS = {
    remember: "Remember",
    understand: "Understand",
    apply: "Apply",
    analyze: "Analyze",
    evaluate: "Evaluate",
    create: "Create",
};

class EducationCurriculumTree extends Component {
    static template = "shiningace_education_curriculum.CurriculumTree";
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");

        this.state = useState({
            loading: true,
            curriculum: null,
            versions: [],           // [{ id, version_label, state, version_number, topics: [...] }]
            selectedVersionId: null,
            openTopicKeys: new Set(),     // Topics expand/collapse
            openSubtopicKeys: new Set(),  // Subtopics expand/collapse (nested inside an open topic)
            addOpenKeys: new Set(),    // which "+ add" inline inputs are currently shown
            addValues: {},             // key -> current text typed in the inline input
        });

        onWillStart(async () => {
            await this.loadTree();
        });
    }

    get curriculumId() {
        const ctx = this.props.action.context || {};
        // `active_id` is the one context key Odoo's action service actually
        // persists into the browser URL/history for client actions (see
        // action_service.js `_getActionParams`/`active_id` handling) — using
        // any other key here means the browser back button can't reconstruct
        // which curriculum was being shown. `curriculum_id` is kept as a
        // fallback for any older callers.
        return ctx.active_id || ctx.curriculum_id || ctx.default_curriculum_id;
    }

    get requestedVersionId() {
        // Optional: lets callers (e.g. the Curriculum Version form's "View
        // Structure Tree" button, or the New Version wizard) preselect a
        // specific version instead of defaulting to published/newest.
        const ctx = this.props.action.context || {};
        return ctx.version_id || null;
    }

    get currentVersion() {
        return this.state.versions.find((v) => v.id === this.state.selectedVersionId) || null;
    }

    async loadTree() {
        const curriculumId = this.curriculumId;
        if (!curriculumId) {
            this.state.loading = false;
            return;
        }

        const [curriculum] = await this.orm.read(
            "education.curriculum", [curriculumId], ["name", "code"]
        );

        const [versions, topics, subtopics, objectives, skills] = await Promise.all([
            this.orm.searchRead(
                "education.curriculum.version",
                [["curriculum_id", "=", curriculumId]],
                ["id", "version_label", "state", "version_number"],
                { order: "version_number desc" }
            ),
            this.orm.searchRead(
                "education.topic",
                [["curriculum_id", "=", curriculumId]],
                ["id", "name", "code", "curriculum_version_id", "approval_state"],
                { order: "sequence asc" }
            ),
            this.orm.searchRead(
                "education.subtopic",
                [["curriculum_id", "=", curriculumId]],
                ["id", "name", "topic_id", "approval_state"],
                { order: "sequence asc" }
            ),
            this.orm.searchRead(
                "education.learning.objective",
                [["curriculum_id", "=", curriculumId]],
                ["id", "name", "topic_id", "subtopic_id", "bloom_level"],
                { order: "sequence asc" }
            ),
            this.orm.searchRead(
                "education.skill",
                [["curriculum_id", "=", curriculumId]],
                ["id", "name", "unique_skill_code", "topic_id", "difficulty_level"],
                { order: "sequence asc" }
            ),
        ]);

        // education.lesson has no direct curriculum_id, only curriculum_version_id,
        // so it's fetched separately once the relevant version ids are known.
        const versionIds = versions.map((v) => v.id);
        const lessonRecords = versionIds.length
            ? await this.orm.searchRead(
                  "education.lesson",
                  [["curriculum_version_id", "in", versionIds]],
                  ["id", "name", "topic_id", "subtopic_id", "duration_minutes", "state", "approval_state"],
                  { order: "sequence asc" }
              )
            : [];

        const topicsByVersion = groupBy(topics, (t) => t.curriculum_version_id && t.curriculum_version_id[0]);
        const subtopicsByTopic = groupBy(subtopics, (s) => s.topic_id && s.topic_id[0]);
        // Topic-level objectives/lessons are, by construction, only the ones with
        // no subtopic_id (a Learning Objective is exactly one of topic-level OR
        // subtopic-level — see education.learning.objective's constraint; Lesson
        // is a plain optional FK so we filter it explicitly below).
        const objectivesByTopic = groupBy(objectives, (o) => o.topic_id && o.topic_id[0]);
        const objectivesBySubtopic = groupBy(objectives, (o) => o.subtopic_id && o.subtopic_id[0]);
        const skillsByTopic = groupBy(skills, (s) => s.topic_id && s.topic_id[0]);
        const topicLevelLessons = lessonRecords.filter((l) => !(l.subtopic_id && l.subtopic_id[0]));
        const lessonsByTopic = groupBy(topicLevelLessons, (l) => l.topic_id && l.topic_id[0]);
        const lessonsBySubtopic = groupBy(lessonRecords, (l) => l.subtopic_id && l.subtopic_id[0]);

        const builtVersions = versions.map((v) => ({
            ...v,
            topics: (topicsByVersion[v.id] || []).map((t) => {
                // Each Subtopic carries its OWN Learning Objectives and Lessons —
                // this is real nesting (Topic > Subtopic > {Objectives, Lessons}),
                // not a flat list with a badge, so the hierarchy the user is
                // adding into is always visually obvious.
                const subtopicsForTopic = (subtopicsByTopic[t.id] || []).map((st) => ({
                    ...st,
                    objectives: objectivesBySubtopic[st.id] || [],
                    lessons: lessonsBySubtopic[st.id] || [],
                }));
                return {
                    ...t,
                    subtopics: subtopicsForTopic,
                    objectives: objectivesByTopic[t.id] || [],
                    skills: skillsByTopic[t.id] || [],
                    lessons: lessonsByTopic[t.id] || [],
                };
            }),
        }));

        this.state.curriculum = curriculum;
        this.state.versions = builtVersions;
        if (!this.state.selectedVersionId || !builtVersions.some((v) => v.id === this.state.selectedVersionId)) {
            const requested = this.requestedVersionId;
            const requestedMatch = requested && builtVersions.find((v) => v.id === requested);
            // Default: the version an explicit caller asked for, else the
            // published version if there is one, else the newest.
            const published = builtVersions.find((v) => v.state === "published");
            this.state.selectedVersionId = (requestedMatch || published || builtVersions[0] || {}).id || null;
        }
        this.state.loading = false;
    }

    onVersionChange(ev) {
        this.state.selectedVersionId = parseInt(ev.target.value);
    }

    openCurriculumDetails() {
        this.openRecord("education.curriculum", this.curriculumId);
    }

    // ── expand/collapse (topics only) ───────────────────────────────────────

    bloomLabel(level) {
        return BLOOM_LABELS[level] || level || "";
    }

    isTopicOpen(topicId) {
        return this.state.openTopicKeys.has(topicId);
    }

    toggleTopic(topicId) {
        if (this.state.openTopicKeys.has(topicId)) {
            this.state.openTopicKeys.delete(topicId);
        } else {
            this.state.openTopicKeys.add(topicId);
        }
        this.state.openTopicKeys = new Set(this.state.openTopicKeys);
    }

    isSubtopicOpen(subtopicId) {
        return this.state.openSubtopicKeys.has(subtopicId);
    }

    toggleSubtopic(subtopicId) {
        if (this.state.openSubtopicKeys.has(subtopicId)) {
            this.state.openSubtopicKeys.delete(subtopicId);
        } else {
            this.state.openSubtopicKeys.add(subtopicId);
        }
        this.state.openSubtopicKeys = new Set(this.state.openSubtopicKeys);
    }

    openRecord(model, id) {
        this.action.doAction({
            type: "ir.actions.act_window",
            res_model: model,
            res_id: id,
            views: [[false, "form"]],
        });
    }

    // ── inline "+ add" rows ──────────────────────────────────────────────────

    isAddOpen(key) {
        return this.state.addOpenKeys.has(key);
    }

    openAdd(key) {
        this.state.addOpenKeys.add(key);
        this.state.addOpenKeys = new Set(this.state.addOpenKeys);
        if (!(key in this.state.addValues)) {
            this.state.addValues[key] = "";
        }
    }

    cancelAdd(key) {
        this.state.addOpenKeys.delete(key);
        this.state.addOpenKeys = new Set(this.state.addOpenKeys);
        this.state.addValues[key] = "";
    }

    onAddInput(key, ev) {
        this.state.addValues[key] = ev.target.value;
    }

    async onAddKeydown(key, submitFn, ev) {
        if (ev.key === "Enter") {
            ev.preventDefault();
            await submitFn();
        } else if (ev.key === "Escape") {
            this.cancelAdd(key);
        }
    }

    async submitAddVersion() {
        const key = "add-version";
        const label = (this.state.addValues[key] || "").trim();
        if (!label) return;
        const curriculumId = this.curriculumId;
        const existingNumbers = this.state.versions.map((v) => v.version_number || 0);
        const nextNumber = existingNumbers.length ? Math.max(...existingNumbers) + 1 : 1;
        const [newId] = await this.orm.create("education.curriculum.version", [{
            curriculum_id: curriculumId,
            version_label: label,
            version_number: nextNumber,
        }]);
        this.cancelAdd(key);
        await this.loadTree();
        this.state.selectedVersionId = newId;
    }

    async submitAddTopic() {
        const key = "add-topic";
        const name = (this.state.addValues[key] || "").trim();
        if (!name || !this.state.selectedVersionId) return;
        await this.orm.create("education.topic", [{ name, curriculum_version_id: this.state.selectedVersionId }]);
        this.cancelAdd(key);
        await this.loadTree();
    }

    async submitAddSubtopic(topicId) {
        const key = `add-subtopic-${topicId}`;
        const name = (this.state.addValues[key] || "").trim();
        if (!name) return;
        const [newId] = await this.orm.create("education.subtopic", [{ name, topic_id: topicId }]);
        this.cancelAdd(key);
        this.state.openTopicKeys.add(topicId);
        this.state.openSubtopicKeys.add(newId);
        await this.loadTree();
    }

    // Topic-level Learning Objective (no subtopic) — subtopic-scoped objectives
    // are added from within that subtopic's own card, see submitAddSubtopicObjective.
    async submitAddObjective(topicId) {
        const key = `add-objective-${topicId}`;
        const name = (this.state.addValues[key] || "").trim();
        if (!name) return;
        await this.orm.create("education.learning.objective", [{ name, topic_id: topicId }]);
        this.cancelAdd(key);
        this.state.openTopicKeys.add(topicId);
        await this.loadTree();
    }

    async submitAddSubtopicObjective(topicId, subtopicId) {
        const key = `add-objective-sub-${subtopicId}`;
        const name = (this.state.addValues[key] || "").trim();
        if (!name) return;
        await this.orm.create("education.learning.objective", [{ name, subtopic_id: subtopicId }]);
        this.cancelAdd(key);
        this.state.openTopicKeys.add(topicId);
        this.state.openSubtopicKeys.add(subtopicId);
        await this.loadTree();
    }

    async submitAddSkill(topicId) {
        const key = `add-skill-${topicId}`;
        const name = (this.state.addValues[key] || "").trim();
        if (!name) return;
        await this.orm.create("education.skill", [{ name, topic_id: topicId }]);
        this.cancelAdd(key);
        this.state.openTopicKeys.add(topicId);
        await this.loadTree();
    }

    // Topic-level Lesson (no subtopic) — subtopic-scoped lessons are added
    // from within that subtopic's own card, see submitAddSubtopicLesson.
    async submitAddLesson(topicId) {
        const key = `add-lesson-${topicId}`;
        const name = (this.state.addValues[key] || "").trim();
        if (!name) return;
        await this.orm.create("education.lesson", [{ name, topic_id: topicId }]);
        this.cancelAdd(key);
        this.state.openTopicKeys.add(topicId);
        await this.loadTree();
    }

    async submitAddSubtopicLesson(topicId, subtopicId) {
        const key = `add-lesson-sub-${subtopicId}`;
        const name = (this.state.addValues[key] || "").trim();
        if (!name) return;
        await this.orm.create("education.lesson", [{ name, topic_id: topicId, subtopic_id: subtopicId }]);
        this.cancelAdd(key);
        this.state.openTopicKeys.add(topicId);
        this.state.openSubtopicKeys.add(subtopicId);
        await this.loadTree();
    }

    // ── delete ───────────────────────────────────────────────────────────────

    async deleteNode(model, id, label) {
        if (!window.confirm(_t("Delete \"%s\"? This cannot be undone.", label))) {
            return;
        }
        try {
            await this.orm.unlink(model, [id]);
            await this.loadTree();
        } catch (e) {
            const message = (e.data && e.data.message) || e.message || _t("Could not delete this record.");
            this.notification.add(message, { type: "danger" });
        }
    }
}

function groupBy(records, keyFn) {
    const map = {};
    for (const rec of records) {
        const key = keyFn(rec);
        if (key === undefined || key === false || key === null) continue;
        if (!map[key]) map[key] = [];
        map[key].push(rec);
    }
    return map;
}

registry.category("actions").add("education_curriculum_tree", EducationCurriculumTree);
