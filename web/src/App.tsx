import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth, RequireRole, RootRedirect } from "./auth/guards";
import { WelcomePage } from "./auth/WelcomePage";
import { LoginPage } from "./auth/LoginPage";
import { SignupPage } from "./auth/SignupPage";
import { ManagerLayout, FieldLayout } from "./shell/AppLayout";
import { Placeholder } from "./shell/Placeholder";
import { PitchesPage } from "./manager/pitches/PitchesPage";
import { ManagerHome } from "./manager/ManagerHome";
import { SettingsPage } from "./manager/SettingsPage";
import { FieldRecorderPage } from "./field/FieldRecorderPage";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        {/* public auth pages — role first (/welcome), then credentials */}
        <Route path="/welcome" element={<WelcomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />

        {/* everything below requires a session */}
        <Route element={<RequireAuth />}>
          {/* Manager interface — managers only */}
          <Route element={<RequireRole role="manager" />}>
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
          </Route>

          {/* Salesperson interface — sales heroes only */}
          <Route element={<RequireRole role="sales" />}>
            <Route path="/field" element={<FieldLayout />}>
              <Route index element={<FieldRecorderPage />} />
              <Route path="pitches" element={<Placeholder title="My pitches" />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="/" element={<RootRedirect />} />
        <Route path="*" element={<RootRedirect />} />
      </Routes>
    </AuthProvider>
  );
}
