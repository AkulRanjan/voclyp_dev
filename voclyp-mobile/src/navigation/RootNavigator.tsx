import React from 'react';
import { useSelector } from 'react-redux';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { RootState } from '../store';
import { LoginScreen } from '../screens/auth/LoginScreen';
import { SignupScreen } from '../screens/auth/SignupScreen';
import { SalesNavigator } from './SalesNavigator';
import { LiveSessionProvider } from '../context/LiveSessionProvider';

const Stack = createNativeStackNavigator();

export function RootNavigator() {
  const { token } = useSelector((state: RootState) => state.auth);

  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      {!token ? (
        <Stack.Group>
          <Stack.Screen name="Login" component={LoginScreen} />
          <Stack.Screen name="Signup" component={SignupScreen} />
        </Stack.Group>
      ) : (
        <Stack.Screen name="SalesApp">
          {() => (
            <LiveSessionProvider>
              <SalesNavigator />
            </LiveSessionProvider>
          )}
        </Stack.Screen>
      )}
    </Stack.Navigator>
  );
}
