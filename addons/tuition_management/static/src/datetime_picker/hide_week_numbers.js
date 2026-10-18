/** @odoo-module **/

import { DateTimePicker } from "@web/core/datetime/datetime_picker";

// Hide the ISO week-number column in every date picker (backend and portal):
// users found it confusing. A caller can still opt back in with
// showWeekNumbers=true.
DateTimePicker.defaultProps = {
    ...DateTimePicker.defaultProps,
    showWeekNumbers: false,
};
