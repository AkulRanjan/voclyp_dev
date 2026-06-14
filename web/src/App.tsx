import { Navigate, Route, Routes } from "react-router-dom";
import { ManagerLayout, FieldLayout } from "./shell/AppLayout";
import { Placeholder } from "./shell/Placeholder";
import { PitchesPage } from "./manager/pitches/PitchesPage";
import { ManagerHome } from "./manager/ManagerHome";
import { SettingsPage } from "./manager/SettingsPage";
import { FieldRecorderPage } from "./field/FieldRecorderPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/manager/pitches" replace />} />

      {/* Manager interface */}
      <Route path="/manager" element={<ManagerLayout />}>
        <Route index element={<ManagerHome />} />
        <Route path="pitches" element={<PitchesPage />} />
        <Route path="conversations" element={<Placeholder title="Conversations" />} />
        <Route path="retailers" element={<Placeholder title="Retailers" />} />
        <Route path="workers" element={<Placeholder title="Workers" />} />
        <Route path="scripts" element={<Placeholder title="Scripts" />} />
        <Route path="campaigns" element={<Placeholder title="Campaigns" />} />
        <Route path="metrics" element={<Placeholder title="Mission Metrics" />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      {/* Salesperson interface */}
      <Route path="/field" element={<FieldLayout />}>
        <Route index element={<FieldRecorderPage />} />
        <Route path="pitches" element={<Placeholder title="My pitches" />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/manager/pitches" replace />} />
    </Routes>
  );
}
