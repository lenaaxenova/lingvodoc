package ru.ispras.lingvodoc.frontend.app.controllers

import com.greencatsoft.angularjs.core.Scope
import com.greencatsoft.angularjs.extensions.ModalInstance
import com.greencatsoft.angularjs.{AbstractController, injectable}

import scala.scalajs.js
import scala.scalajs.js.annotation.JSExport

import org.scalajs.dom.console

@js.native
trait ExceptionHandlerScope extends Scope {
  var message: String = js.native
  var messageHtml: String = js.native
  var causeMessage: String = js.native
  var causeMessageHtml: String = js.native
  var stackTrace: String = js.native
  var stackTraceHtml: String = js.native
}

@injectable("ExceptionHandlerController")
class ExceptionHandlerController(scope: ExceptionHandlerScope,
                                 instance: ModalInstance[Unit],
                                 params: js.Dictionary[js.Function0[js.Any]]) extends AbstractController[ExceptionHandlerScope](scope) {

  params("exception") match {

    case e: Throwable =>
      scope.message = e.getMessage

      e.getCause match {
        case cause: Throwable =>
          scope.causeMessage = e.getCause.getMessage
          scope.stackTrace = e.getCause.getStackTrace.mkString("\n")
        case _ =>
          scope.causeMessage = e.getMessage
          scope.stackTrace = e.getStackTrace.mkString("\n")
      }

      scope.messageHtml = scope.message.replaceAll("\n", "<br>")

      scope.causeMessageHtml =
        if (scope.causeMessage != null)
          scope.causeMessage.replaceAll("\n", "<br>")
        else "null"

      scope.stackTraceHtml = scope.stackTrace.replaceAll("\n", "<br>")

    case _ =>
      scope.message = ""
      scope.causeMessage = ""
      scope.stackTrace = ""

      scope.messageHtml = ""
      scope.causeMessageHtml = ""
      scope.stackTraceHtml = ""
  }

  @JSExport
  def ok(): Unit = {
    instance.dismiss(())
  }

  @JSExport
  def report(): Unit = {
    instance.dismiss(())
  }
}

