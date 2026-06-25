import React from 'react';
import { Provider } from 'react-redux';
import { PersistGate } from 'redux-persist/integration/react';
import { NavigationContainer } from '@react-navigation/native';
import { ActivityIndicator, View } from 'react-native';
import { store, persistor } from './store';
import { RootNavigator } from './navigation/RootNavigator';
import { AuthTokenSync } from './auth/AuthTokenSync';
import { initAPIClient } from './api/client';
import { API_BASE, BRAND } from './config';

initAPIClient(API_BASE);

export default function App() {
  return (
    <Provider store={store}>
      <PersistGate
        loading={
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            <ActivityIndicator size="large" color={BRAND.indigo} />
          </View>
        }
        persistor={persistor}
      >
        <AuthTokenSync />
        <NavigationContainer>
          <RootNavigator />
        </NavigationContainer>
      </PersistGate>
    </Provider>
  );
}
