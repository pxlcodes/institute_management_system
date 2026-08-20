from __future__ import annotations


def attendance_user_choices(app, person_type: str, person_id: int | None = None):
    """Return safe device-user choices and the person's current selection.

    Users actively linked to somebody else are intentionally hidden. Reassigning
    those records remains available from the central Attendance Device screen.
    """
    choices: dict[str, str] = {}
    current_label = ""
    for raw_row in app.services.attendance.repository.device_users():
        row = dict(raw_row)
        is_current = (
            row.get("status") == "Active"
            and row.get("person_type") == person_type
            and row.get("person_id") is not None
            and person_id is not None
            and int(row["person_id"]) == int(person_id)
        )
        is_unmapped = row.get("status") == "Unmapped"
        if not (is_unmapped or is_current):
            continue

        device_id = str(row["device_user_id"])
        device_name = str(row.get("device_name") or "Unnamed device user").strip()
        label = f"{device_id} - {device_name}"
        if is_current:
            label += "  [Currently linked]"
            current_label = label
        choices[label] = device_id
    return choices, current_label


def selected_attendance_device(selected_label: str, choices: dict[str, str]) -> str | None:
    selected_label = selected_label.strip()
    if not selected_label:
        return None
    device_user_id = choices.get(selected_label)
    if device_user_id is None:
        raise ValueError("Select an attendance user from the dropdown list.")
    return device_user_id
