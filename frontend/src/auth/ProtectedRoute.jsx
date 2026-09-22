import { Navigate, Outlet } from "react-router-dom";
import { useAuth } from "./AuthProvider";

export default function ProtectedRoute() {
    const {credential } = useAuth();

    if (!credential) {
        return <Navigate to='/login' replace />;
    }

    return <Outlet />;
}