from azure_data_lake_fs.publisher import ChangePublisher


def test_publish_serializes_event_as_json() -> None:
    sent: list[str] = []
    publisher = ChangePublisher(send=sent.append)

    publisher.publish({"event_type": "delete", "file_path": "a/b.txt"})

    assert sent == ['{"event_type": "delete", "file_path": "a/b.txt"}']
