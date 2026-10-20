from flask import Flask, jsonify, request
from datetime import datetime, timezone
import json
import os

app = Flask(__name__)

COURSES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "courses.json")
VALID_STATUSES = ["Not Started", "In Progress", "Completed"]


def ensure_courses_file():
    try:
        if not os.path.exists(COURSES_FILE):
            with open(COURSES_FILE, "w", encoding="utf-8") as file:
                json.dump([], file, indent=2)
    except OSError as e:
        raise RuntimeError(f"Could not create courses file: {e}")


def load_courses():
    try:
        ensure_courses_file()
        with open(COURSES_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            return []
        return data
    except FileNotFoundError:
        raise RuntimeError("Courses file was not found.")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Courses file contains invalid JSON: {e}")
    except OSError as e:
        raise RuntimeError(f"Could not read courses file: {e}")


def save_courses(courses):
    try:
        with open(COURSES_FILE, "w", encoding="utf-8") as file:
            json.dump(courses, file, indent=2)
    except OSError as e:
        raise RuntimeError(f"Could not write to courses file: {e}")


def validate_status(status):
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status. Must be one of: {', '.join(VALID_STATUSES)}")


def validate_target_date(target_date):
    try:
        datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid target_date format. Use YYYY-MM-DD.")


def validate_course_data(data, require_all_fields=True):
    if not isinstance(data, dict):
        raise ValueError("Request body must be a JSON object.")

    required_fields = ["name", "description", "target_date", "status"]

    if require_all_fields:
        missing_fields = [field for field in required_fields if field not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

    validated = {}

    if "name" in data:
        name = data["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Field 'name' is required and must be a non-empty string.")
        validated["name"] = name.strip()

    if "description" in data:
        description = data["description"]
        if not isinstance(description, str) or not description.strip():
            raise ValueError("Field 'description' is required and must be a non-empty string.")
        validated["description"] = description.strip()

    if "target_date" in data:
        target_date = data["target_date"]
        if not isinstance(target_date, str):
            raise ValueError("Field 'target_date' must be a string in YYYY-MM-DD format.")
        validate_target_date(target_date)
        validated["target_date"] = target_date

    if "status" in data:
        status = data["status"]
        if not isinstance(status, str):
            raise ValueError("Field 'status' must be a string.")
        validate_status(status)
        validated["status"] = status

    return validated


def get_next_course_id(courses):
    if not courses:
        return 1
    return max(course.get("id", 0) for course in courses) + 1


def find_course_by_id(courses, course_id):
    for course in courses:
        if course.get("id") == course_id:
            return course
    return None


@app.route("/api/courses", methods=["POST"], strict_slashes=False)
def create_course():
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    try:
        validated_data = validate_course_data(data, require_all_fields=True)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        courses = load_courses()
        new_course = {
            "id": get_next_course_id(courses),
            "name": validated_data["name"],
            "description": validated_data["description"],
            "target_date": validated_data["target_date"],
            "status": validated_data["status"],
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }

        courses.append(new_course)
        save_courses(courses)
        return jsonify(new_course), 201
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/courses", methods=["GET"], strict_slashes=False)
def get_all_courses():
    try:
        courses = load_courses()
        return jsonify(courses), 200
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/courses/<int:course_id>", methods=["GET"], strict_slashes=False)
def get_course(course_id):
    try:
        courses = load_courses()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    course = find_course_by_id(courses, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404

    return jsonify(course), 200


@app.route("/api/courses/<int:course_id>", methods=["PUT"], strict_slashes=False)
def update_course(course_id):
    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"error": "Request body must be valid JSON."}), 400

    try:
        validated_data = validate_course_data(data, require_all_fields=False)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        courses = load_courses()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    course = find_course_by_id(courses, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404

    course.update(validated_data)

    try:
        save_courses(courses)
        return jsonify(course), 200
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/courses/<int:course_id>", methods=["DELETE"], strict_slashes=False)
def delete_course(course_id):
    try:
        courses = load_courses()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    course = find_course_by_id(courses, course_id)
    if course is None:
        return jsonify({"error": "Course not found."}), 404

    updated_courses = [c for c in courses if c.get("id") != course_id]

    try:
        save_courses(updated_courses)
        return jsonify({
            "message": "Course deleted successfully.",
            "deleted_course": course
        }), 200
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/courses/stats", methods=["GET"], strict_slashes=False)
def get_course_stats():
    """
    Return statistics for all courses:
    - total number of courses
    - number of courses by status
    """
    try:
        courses = load_courses()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 500

    status_counts = {
        "Not Started": 0,
        "In Progress": 0,
        "Completed": 0
    }

    for course in courses:
        status = course.get("status")
        if status in status_counts:
            status_counts[status] += 1

    stats = {
        "total_courses": len(courses),
        "by_status": status_counts
    }

    return jsonify(stats), 200

if __name__ == "__main__":
    app.run(debug=True)