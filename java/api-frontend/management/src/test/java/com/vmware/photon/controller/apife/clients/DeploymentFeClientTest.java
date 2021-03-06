/*
 * Copyright 2015 VMware, Inc. All Rights Reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not
 * use this file except in compliance with the License.  You may obtain a copy of
 * the License at http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software distributed
 * under the License is distributed on an "AS IS" BASIS, without warranties or
 * conditions of any kind, EITHER EXPRESS OR IMPLIED.  See the License for the
 * specific language governing permissions and limitations under the License.
 */

package com.vmware.photon.controller.apife.clients;

import com.vmware.photon.controller.api.ClusterConfiguration;
import com.vmware.photon.controller.api.ClusterConfigurationSpec;
import com.vmware.photon.controller.api.ClusterType;
import com.vmware.photon.controller.api.DeploymentCreateSpec;
import com.vmware.photon.controller.api.Project;
import com.vmware.photon.controller.api.ResourceList;
import com.vmware.photon.controller.api.Task;
import com.vmware.photon.controller.api.Tenant;
import com.vmware.photon.controller.api.Vm;
import com.vmware.photon.controller.apife.backends.DeploymentBackend;
import com.vmware.photon.controller.apife.backends.HostBackend;
import com.vmware.photon.controller.apife.backends.ProjectBackend;
import com.vmware.photon.controller.apife.backends.TaskBackend;
import com.vmware.photon.controller.apife.backends.TaskCommandExecutorService;
import com.vmware.photon.controller.apife.backends.TenantBackend;
import com.vmware.photon.controller.apife.backends.VmBackend;
import com.vmware.photon.controller.apife.commands.tasks.TaskCommand;
import com.vmware.photon.controller.apife.commands.tasks.TaskCommandFactory;
import com.vmware.photon.controller.apife.entities.TaskEntity;
import com.vmware.photon.controller.common.Constants;

import com.google.common.base.Optional;
import com.google.common.collect.ImmutableList;
import org.testng.annotations.BeforeMethod;
import org.testng.annotations.DataProvider;
import org.testng.annotations.Test;
import static org.hamcrest.MatcherAssert.assertThat;
import static org.hamcrest.Matchers.is;
import static org.mockito.Matchers.any;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.powermock.api.mockito.PowerMockito.verifyNoMoreInteractions;

import java.util.List;
import java.util.concurrent.ExecutorService;

/**
 * Tests {@link DeploymentFeClient}.
 */
public class DeploymentFeClientTest {
  private DeploymentFeClient feClient;

  private TaskBackend taskBackend;
  private DeploymentBackend deploymentBackend;
  private VmBackend vmBackend;
  private HostBackend hostBackend;
  private TenantBackend tenantBackend;
  private ProjectBackend projectBackend;
  private TaskCommandFactory commandFactory;
  private ExecutorService executorService;

  private void setUpCommon() {
    taskBackend = mock(TaskBackend.class);
    deploymentBackend = mock(DeploymentBackend.class);
    vmBackend = mock(VmBackend.class);
    hostBackend = mock(HostBackend.class);
    tenantBackend = mock(TenantBackend.class);
    projectBackend = mock(ProjectBackend.class);

    commandFactory = mock(TaskCommandFactory.class);
    executorService = mock(TaskCommandExecutorService.class);

    feClient = new DeploymentFeClient(
        taskBackend, deploymentBackend, vmBackend, hostBackend, tenantBackend, projectBackend, commandFactory,
        executorService);
  }

  /**
   * dummy test to keep IntelliJ happy.
   */
  @Test
  private void dummy() {
  }

  /**
   * Tests the create method.
   */
  public class CreateTest {
    @BeforeMethod
    public void setUp() {
      setUpCommon();
    }

    @Test
    public void testTaskIsCreateAndSubmitted() throws Throwable {
      DeploymentCreateSpec spec = new DeploymentCreateSpec();
      TaskEntity taskEntity = new TaskEntity();
      doReturn(taskEntity).when(deploymentBackend).prepareCreateDeployment(spec);

      Task task = new Task();
      doReturn(task).when(taskBackend).getApiRepresentation(taskEntity);

      Task resp = feClient.create(spec);
      assertThat(resp, is(task));
    }
  }

  /**
   * Tests the perform method.
   */
  public class PerformDeploymentTest {
    @BeforeMethod
    public void setUp() {
      setUpCommon();
    }

    @Test
    public void testTaskIsCreated() throws Throwable {
      String deploymentId = "deployment-id";
      TaskEntity taskEntity = new TaskEntity();
      doReturn(taskEntity).when(deploymentBackend).prepareDeploy(deploymentId);

      Task task = new Task();
      doReturn(task).when(taskBackend).getApiRepresentation(taskEntity);

      TaskCommand command = mock(TaskCommand.class);
      doReturn(command).when(commandFactory).create(taskEntity);

      Task resp = feClient.perform("deployment-id");
      assertThat(resp, is(task));
      verify(executorService).submit(command);
    }
  }

  /**
   * Tests the delete and destroy methods.
   */
  public class DeleteTest {
    @BeforeMethod
    public void setUp() {
      setUpCommon();
    }

    @Test
    public void testDelete() throws Throwable {
      TaskEntity taskEntity = new TaskEntity();
      doReturn(taskEntity).when(deploymentBackend).prepareDeleteDeployment(any(String.class));

      Task task = new Task();
      doReturn(task).when(taskBackend).getApiRepresentation(taskEntity);

      TaskCommand command = mock(TaskCommand.class);
      doReturn(command).when(commandFactory).create(taskEntity);

      Task resp = feClient.delete("dummy-deployment-id");
      assertThat(resp, is(task));
      //delete creates a completed task so no more execution is required.
      verifyNoMoreInteractions(executorService);
    }

    @Test
    public void testDestroy() throws Throwable {
      TaskEntity taskEntity = new TaskEntity();
      doReturn(taskEntity).when(deploymentBackend).prepareDestroy(any(String.class));

      Task task = new Task();
      doReturn(task).when(taskBackend).getApiRepresentation(taskEntity);

      TaskCommand command = mock(TaskCommand.class);
      doReturn(command).when(commandFactory).create(taskEntity);

      Task resp = feClient.destroy("dummy-deployment-id");
      assertThat(resp, is(task));
      verify(executorService).submit(command);
    }
  }

  /**
   * Tests the listVms method.
   */
  public class ListVmsTest {
    String deploymentId;
    Tenant tenant;
    Project project;
    Vm vm;

    @BeforeMethod
    public void setUp() throws Throwable {
      setUpCommon();

      deploymentId = "deployment-id";
      doReturn(null).when(deploymentBackend).findById(deploymentId);

      tenant = new Tenant();
      tenant.setId("mgmt-tenant-id");
      tenant.setName(Constants.TENANT_NAME);
      doReturn(ImmutableList.of(tenant)).when(tenantBackend).filter(
          Optional.of(Constants.TENANT_NAME));

      project = new Project();
      project.setId("mgmt-project-id");
      project.setName(Constants.PROJECT_NAME);
      doReturn(ImmutableList.of(project)).when(projectBackend).filter(
          tenant.getId(), Optional.of(Constants.PROJECT_NAME));

      vm = new Vm();
      vm.setId("mgmt-vm-id");
      doReturn(ImmutableList.of(vm)).when(vmBackend).filterByProject(project.getId());
    }

    /**
     * Test a successful invocation of the method.
     *
     * @throws Throwable
     */
    @Test
    public void testSuccess() throws Throwable {
      ResourceList list = feClient.listVms(deploymentId);
      assertThat(list.getItems().size(), is(1));
      assertThat((Vm) list.getItems().get(0), is(vm));
    }

    /**
     * Test scenario when either no management tenant could be found or
     * more than one tenant matched the name.
     *
     * @param message
     * @param tenantList
     * @throws Throwable
     */
    @Test(dataProvider = "NotFoundTenantData")
    public void testNotFoundTenant(String message, List<Tenant> tenantList) throws Throwable {
      doReturn(tenantList).when(tenantBackend).filter(Optional.of(Constants.TENANT_NAME));
      ResourceList list = feClient.listVms(deploymentId);
      assertThat(list.getItems().size(), is(0));
    }

    @DataProvider(name = "NotFoundTenantData")
    Object[][] getNotFoundTenantData() {
      return new Object[][]{
          {"No tenants", ImmutableList.of()},
          {"Multiple tenants", ImmutableList.of(new Tenant(), new Tenant())}
      };
    }

    /**
     * Test scenario when either management project could not be found or
     * more than one project matched the name.
     *
     * @param message
     * @param projectList
     * @throws Throwable
     */
    @Test(dataProvider = "NotFoundProjectData")
    public void testNotFoundProject(String message, List<Tenant> projectList) throws Throwable {
      doReturn(projectList).when(projectBackend).filter(tenant.getId(), Optional.of(Constants.PROJECT_NAME));
      ResourceList list = feClient.listVms(deploymentId);
      assertThat(list.getItems().size(), is(0));
    }

    @DataProvider(name = "NotFoundProjectData")
    Object[][] getNotFoundProjectData() {
      return new Object[][]{
          {"No projects", ImmutableList.of()},
          {"Multiple projects", ImmutableList.of(new Project(), new Project())}
      };
    }
  }

  /**
   * Tests the migration methods.
   */
  public class PerformDeploymentMigrationTest {
    @BeforeMethod
    public void setUp() {
      setUpCommon();
    }

    @Test
    public void testInitializeMigrationTaskIsCreated() throws Throwable {
      String deploymentId = "deployment-id";
      String sourceAddress = "sourceAddress";
      TaskEntity taskEntity = new TaskEntity();
      doReturn(taskEntity).when(deploymentBackend).prepareInitializeMigrateDeployment(sourceAddress, deploymentId);

      Task task = new Task();
      doReturn(task).when(taskBackend).getApiRepresentation(taskEntity);

      TaskCommand command = mock(TaskCommand.class);
      doReturn(command).when(commandFactory).create(taskEntity);

      Task resp = feClient.initializeDeploymentMigration(sourceAddress, deploymentId);
      assertThat(resp, is(task));
      verify(executorService).submit(command);
    }

    @Test
    public void testFinalizeMigrationTaskIsCreated() throws Throwable {
      String deploymentId = "deployment-id";
      String sourceAddress = "sourceAddress";
      TaskEntity taskEntity = new TaskEntity();
      doReturn(taskEntity).when(deploymentBackend).prepareFinalizeMigrateDeployment(sourceAddress, deploymentId);

      Task task = new Task();
      doReturn(task).when(taskBackend).getApiRepresentation(taskEntity);

      TaskCommand command = mock(TaskCommand.class);
      doReturn(command).when(commandFactory).create(taskEntity);

      Task resp = feClient.finalizeDeploymentMigration(sourceAddress, deploymentId);
      assertThat(resp, is(task));
      verify(executorService).submit(command);
    }
  }

  /**
   * Tests the config cluster method.
   */
  public class ConfigClusterTest {
    String deploymentId;
    ClusterConfiguration configuration;

    @BeforeMethod
    public void setUp() throws Throwable {
      setUpCommon();

      deploymentId = "deployment-id";
      doReturn(null).when(deploymentBackend).findById(deploymentId);

      configuration = new ClusterConfiguration();
      configuration.setType(ClusterType.KUBERNETES);
      configuration.setImageId("imageId");

      doReturn(configuration).when(deploymentBackend).configureCluster(any(ClusterConfigurationSpec.class));
    }

    @Test
    public void testSuccess() throws Throwable {
      ClusterConfiguration config = feClient.configureCluster(deploymentId, new ClusterConfigurationSpec());

      assertThat(config.getType(), is(ClusterType.KUBERNETES));
      assertThat(config.getImageId(), is("imageId"));
    }
  }
}
