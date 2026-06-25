import { Route, Routes } from "react-router-dom";
import { AuthProvider } from "./auth/AuthContext";
import { RequireAuth, RequireManager, RequireRole, RootRedirect } from "./auth/guards";
import { WelcomePage } from "./auth/WelcomePage";
import { LoginPage } from "./auth/LoginPage";
import { SignupPage } from "./auth/SignupPage";
import { ManagerLayout, FieldLayout } from "./shell/AppLayout";
import { Placeholder } from "./shell/Placeholder";
import { PitchesPage } from "./manager/pitches/PitchesPage";
import { ManagerHome } from "./manager/ManagerHome";
import { SettingsPage } from "./manager/SettingsPage";
import { FieldRecorderPage } from "./field/FieldRecorderPage";
import { LiveFloorPage } from "./manager/live/LiveFloorPage";
import { StoresComparePage } from "./manager/stores/StoresComparePage";
import { StoreDetailPage } from "./manager/stores/StoreDetailPage";

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/welcome" element={<WelcomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />

        <Route element={<RequireAuth />}>
          <Route element={<RequireManager />}>
            <Route path="/manager" element={<ManagerLayout />}>
              <Route index element={<ManagerHome />} />
              <Route path="live" element={<LiveFloorPage />} />
              <Route path="stores" element={<StoresComparePage />} />
              <Route path="stores/:storeId" element={<StoreDetailPage />} />
              <Route path="pitches" element={<PitchesPage />} />
              <Route path="conversations" element={<Placeholder title="Conversations" />} />
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Route>

          <Route element={<RequireRole role="sales" />}>
            <Route path="/field" element={<FieldLayout />}>
              <Route index element={<FieldRecorderPage />} />
              <Route path="pitches" element={<PitchesPage />} />
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
