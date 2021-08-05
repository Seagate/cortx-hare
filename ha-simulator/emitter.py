from ha.core.action_handler.action_handler import NodeFailureActionHandler
from ha.core.event_manager.event_manager import EventManager
from ha.core.event_manager.subscribe_event import SubscribeEvent
from ha.core.system_health.const import HEALTH_STATUSES
from ha.core.system_health.model.health_event import HealthEvent


def main():
    component = "hare"
    resource_type = "node"
    state = "offline"
    # import pudb.remote
    # pudb.remote.set_trace(term_size=(130, 40), port=9998)

    # Before submitting a fake event, we need to register the component
    # (just to make sure that the message will be sent)
    EventManager.get_instance().subscribe(
        component, [SubscribeEvent(resource_type, [state])])
    handler = NodeFailureActionHandler()

    event = HealthEvent("event_id", HEALTH_STATUSES.OFFLINE.value, "severity",
                        "1", "1", "e766bd52-c19c-45b6-9c91-663fd8203c2e",
                        "storage-set-1", "localhost", "srvnode-1.mgmt.public",
                        "node", "16215009572", "iem", "Description")
    handler.publish_event(event)


if __name__ == "__main__":
    main()
