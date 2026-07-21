import SupersetDashboard from "../../components/SupersetDashboard";

export default function CurrentStateDashboard() {
  return (
    <SupersetDashboard
      title="CURRENT STATE ANALYTICS"
      description="Visualizing the inefficiencies, space utilization, and safety conflicts of the current reality warehouse layout."
      // 🔴 IMPORTANT: Replace this with the UUID you get from Superset's "Embed Dashboard" menu
      embeddedId="8682bd37-3bd5-43bb-b1a8-2f6eb534dd5c"
    />
  );
}
