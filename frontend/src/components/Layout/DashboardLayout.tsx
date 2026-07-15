import { useEffect, useState } from 'react';
import Sidebar from './Sidebar';
import Navbar from './Navbar';
import { authApi } from '../../services/api';

interface DashboardLayoutProps {
  children: React.ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const [user, setUser] = useState<any>(null);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const response = await authApi.get('/me');
        setUser(response.data);
      } catch (error) {
        console.error('Error fetching user for layout:', error);
      }
    };
    fetchUser();
  }, []);

  return (
    <div className="flex min-h-screen bg-yeikar-tertiary">
      <Sidebar
        roles={user?.roles?.map((r: any) => r.nombre) || []}
        nombreUsuario={user?.nombre_usuario || 'Usuario'}
      />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Navbar />
        <main className="flex-1 overflow-x-hidden overflow-y-auto bg-yeikar-tertiary p-8">
          <div className="max-w-7xl mx-auto space-y-6">
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}
