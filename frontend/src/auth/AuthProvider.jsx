import { createContext, useContext, useState } from "react";
import { GoogleOAuthProvider, GoogleLogin } from "@react-oauth/google";
import { jwtDecode } from "jwt-decode";

const AuthContext = createContext();

export function AuthProvider({ children }) {
    const [credential, setCredentials] = useState(
        () => sessionStorage.getItem('google_credential')
    );

    const [user, setUser] = useState(() => {
        const raw = sessionStorage.getItem("google_user");
        return raw ? JSON.parse(raw) : null;
    });

    const login = (response) => {
        const payload = jwtDecode(response.credential);

        const userData = {
            name: payload.name,
            email: payload.email,
            picture: payload.picture,
            sub: payload.sub,
        };

        sessionStorage.setItem('google_credential', response.credential);
        sessionStorage.setItem("google_user", JSON.stringify(userData));
        setCredentials(response.credential);
        setUser(userData);
    };

    const logout = () => {
        sessionStorage.removeItem('google_credential');
        sessionStorage.removeItem("google_user");
        setCredentials(null);
        setUser(null);
    };

    return (
        <AuthContext.Provider value={{ credential, user, login, logout }}>
            <GoogleOAuthProvider clientId={import.meta.env.VITE_GOOGLE_CLIENT_ID}>
                {children}
            </GoogleOAuthProvider>
        </AuthContext.Provider>
    );
}

export function useAuth() {
    return useContext(AuthContext);
}

export function GoogleSignIn() {
    const { login } = useAuth();

    return (
        <div className="google-login-wrap">
            <GoogleLogin
                onSuccess={login}
                onError={() => console.error("Google login failed")}
                theme="filled_black"
                size="large"
                text="signin_with"
                shape="pill"
                logo_alignment="left"
                width="280"
            />
        </div>
    );
}