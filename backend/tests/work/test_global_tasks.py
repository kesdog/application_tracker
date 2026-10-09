def make_application(client, title="Engineer", company="Example"):
    response = client.post("/api/applications", json={
        "job_title": title, "company": company, "date_applied": "2026-09-24",
        "email_reference": f"{company} message",
    })
    assert response.status_code == 201
    return response.json()


def test_global_tasks_only_include_application_linked_tasks_and_date_order(client):
    one = make_application(client, "Engineer", "One")
    two = make_application(client, "Designer", "Two")
    later = client.post(f"/api/applications/{one['id']}/tasks", json={"title": "Later", "due_at": "2026-10-02T10:00:00Z"}).json()
    sooner = client.post(f"/api/applications/{two['id']}/tasks", json={"title": "Sooner", "due_at": "2026-09-29T10:00:00Z"}).json()
    no_date = client.post(f"/api/applications/{one['id']}/tasks", json={"title": "No date"}).json()
    rows = client.get("/api/tasks").json()
    assert [row["id"] for row in rows] == [sooner["id"], later["id"], no_date["id"]]
    assert [row["application"]["id"] for row in rows] == [two["id"], one["id"], one["id"]]
