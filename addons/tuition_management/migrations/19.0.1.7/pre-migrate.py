"""Remove duplicate enquiry stages, keeping only the lowest id per name."""


def migrate(cr, version):
    if not version:
        return
    # Remove stages that are not in the official set
    official_names = ('New', 'Demo Scheduled', 'Enrolled', 'Lost')

    # Reassign enquiries on non-official stages to 'New' (min id)
    cr.execute("""
        UPDATE enquiry
        SET stage_id = (SELECT MIN(id) FROM enquiry_stage WHERE name = 'New')
        WHERE stage_id IN (
            SELECT id FROM enquiry_stage WHERE name NOT IN %s
        )
    """, (official_names,))

    # Reassign enquiries pointing to duplicate stages to the kept (min id) stage
    cr.execute("""
        UPDATE enquiry
        SET stage_id = keeper.min_id
        FROM (
            SELECT name, MIN(id) AS min_id
            FROM enquiry_stage
            GROUP BY name
        ) keeper
        JOIN enquiry_stage es ON es.name = keeper.name AND es.id != keeper.min_id
        WHERE enquiry.stage_id = es.id
    """)

    # Delete non-official stages (e.g. 'Demo Completed')
    cr.execute("""
        DELETE FROM enquiry_stage WHERE name NOT IN %s
    """, (official_names,))

    # Delete duplicate stage rows (keep lowest id per name)
    cr.execute("""
        DELETE FROM enquiry_stage
        WHERE id NOT IN (
            SELECT MIN(id) FROM enquiry_stage GROUP BY name
        )
    """)

    # Remove orphan ir_model_data pointing to deleted stages
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model = 'enquiry.stage'
          AND res_id NOT IN (SELECT id FROM enquiry_stage)
    """)